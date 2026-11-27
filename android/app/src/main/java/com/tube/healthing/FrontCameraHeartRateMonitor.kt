@file:OptIn(androidx.camera.camera2.interop.ExperimentalCamera2Interop::class)

package com.tube.healthing

import android.annotation.SuppressLint
import android.content.Context
import android.hardware.camera2.CaptureRequest
import android.os.Handler
import android.os.Looper
import android.util.Log
import androidx.camera.camera2.interop.Camera2CameraControl
import androidx.camera.camera2.interop.Camera2Interop
import androidx.camera.camera2.interop.CaptureRequestOptions
import androidx.camera.core.Camera
import androidx.camera.core.CameraControl
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import kotlin.math.roundToInt
import kotlin.math.sqrt

/**
 * Front-camera fingertip PPG with screen green fill-light (no rear torch).
 *
 * State: [WaitingForFinger] → [Measuring] (15 s) → [Completed] (median BPM).
 */
class FrontCameraHeartRateMonitor(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
    private val previewView: PreviewView,
    private val listener: Listener,
) {
    sealed class MeasurementState {
        data class WaitingForFinger(val hint: String) : MeasurementState()
        data class Measuring(
            val progress: Float,
            val remainingSeconds: Int,
            val currentBpm: Int,
        ) : MeasurementState()
        data class Completed(val finalBpm: Int) : MeasurementState()
    }

    interface Listener {
        fun onState(state: MeasurementState)
        fun onWaveUpdated(value: Float)
        fun onCompleted(medianBpm: Int, beats15s: Int)
        fun onError(message: String)
    }

    private val mainHandler = Handler(Looper.getMainLooper())
    private val cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()

    private var cameraProvider: ProcessCameraProvider? = null
    private var cameraControl: CameraControl? = null
    private var camera: Camera? = null
    private var starting = false

    private var isExposureLocked = false
    private var isCompleted = false

    private val targetDurationMs = 15_000L
    private var measureStartTimeMs: Long? = null
    private val validBpmReadings = mutableListOf<Int>()

    private val signalBuffer = mutableListOf<Double>()
    private val timeBuffer = mutableListOf<Long>()
    private val maxBufferSize = 240
    private var latestBpm = 0

    private var prevRaw = 0.0
    private var prevHighPass = 0.0
    private var prevLowPass = 0.0

    @Volatile
    var lastState: MeasurementState = MeasurementState.WaitingForFinger("請將指腹輕蓋住上方前置鏡頭與綠光區")
        private set

    fun start() {
        if (!lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) return
        if (starting) return
        starting = true
        resetInternalState()
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener({
            if (!lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) {
                starting = false
                return@addListener
            }
            try {
                val provider = future.get()
                cameraProvider = provider
                previewView.implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                previewView.scaleType = PreviewView.ScaleType.FILL_CENTER

                val preview = Preview.Builder().build().also {
                    it.setSurfaceProvider(previewView.surfaceProvider)
                }

                val analysisBuilder = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)

                Camera2Interop.Extender(analysisBuilder)
                    .setCaptureRequestOption(
                        CaptureRequest.FLASH_MODE,
                        CaptureRequest.FLASH_MODE_OFF
                    )

                val analysis = analysisBuilder.build().also { useCase ->
                    useCase.setAnalyzer(cameraExecutor) { imageProxy ->
                        processFrame(imageProxy)
                    }
                }

                provider.unbindAll()
                val bound = CameraBind.bindFrontOnly(lifecycleOwner, provider, preview, analysis)
                camera = bound
                cameraControl = bound?.cameraControl
                if (bound == null) {
                    emitError("打不開前置鏡頭。請確認自拍鏡頭可用。")
                } else {
                    emitState(MeasurementState.WaitingForFinger("請將指腹輕蓋住上方前置鏡頭與綠光區"))
                }
            } catch (e: Exception) {
                Log.e(TAG, "前置相機啟動失敗", e)
                emitError(e.message ?: "無法開啟前置鏡頭")
            } finally {
                starting = false
            }
        }, ContextCompat.getMainExecutor(context))
    }

    fun remeasure() {
        stopCameraOnly()
        resetInternalState()
        emitState(MeasurementState.WaitingForFinger("請將指腹輕蓋住上方前置鏡頭與綠光區"))
        start()
    }

    fun pause() {
        lockCameraExposure(false)
        stopCameraOnly()
        starting = false
        if (lastState is MeasurementState.Measuring) {
            resetInternalState()
            emitState(MeasurementState.WaitingForFinger("已暫停 — 返回後請再蓋住鏡頭"))
        }
    }

    fun stop() {
        lockCameraExposure(false)
        stopCameraOnly()
        starting = false
        try {
            cameraExecutor.shutdownNow()
        } catch (_: Exception) {
        }
    }

    @SuppressLint("UnsafeOptInUsageError")
    private fun processFrame(imageProxy: ImageProxy) {
        try {
            if (isCompleted) return

            val greenAvg = calculateCenterGreenAverage(imageProxy)
            val currentTime = System.currentTimeMillis()

            // With pure-green fill-light, covered fingertip green sits ~30–235.
            if (greenAvg in 30.0..235.0) {
                if (!isExposureLocked && signalBuffer.size > 30) {
                    lockCameraExposure(true)
                    isExposureLocked = true
                    measureStartTimeMs = currentTime
                }

                val filteredValue = applyBandpassFilter(greenAvg)
                mainHandler.post { listener.onWaveUpdated(filteredValue.toFloat()) }

                signalBuffer.add(filteredValue)
                timeBuffer.add(currentTime)

                if (signalBuffer.size > maxBufferSize) {
                    signalBuffer.removeAt(0)
                    timeBuffer.removeAt(0)
                    detectPeaksAndCalculateBpm()
                }

                val startTime = measureStartTimeMs
                if (startTime != null) {
                    val elapsedMs = currentTime - startTime
                    val progress = (elapsedMs.toFloat() / targetDurationMs).coerceIn(0f, 1f)
                    val remainingSec =
                        ((targetDurationMs - elapsedMs) / 1000L).toInt().coerceAtLeast(0)

                    if (elapsedMs >= targetDurationMs) {
                        finishMeasurement()
                    } else {
                        emitState(
                            MeasurementState.Measuring(
                                progress = progress,
                                remainingSeconds = remainingSec,
                                currentBpm = latestBpm,
                            )
                        )
                    }
                } else {
                    emitState(MeasurementState.WaitingForFinger("偵測到手指，正在鎖定補光曝光..."))
                }
            } else {
                if (isExposureLocked) {
                    lockCameraExposure(false)
                    isExposureLocked = false
                }
                measureStartTimeMs = null
                signalBuffer.clear()
                timeBuffer.clear()
                validBpmReadings.clear()
                latestBpm = 0
                prevRaw = 0.0
                prevHighPass = 0.0
                prevLowPass = 0.0

                val hint = if (greenAvg < 30.0) {
                    "光線過暗，請讓指腹同時接觸螢幕綠光區"
                } else {
                    "請將指腹輕貼前置鏡頭"
                }
                emitState(MeasurementState.WaitingForFinger(hint))
            }
        } finally {
            imageProxy.close()
        }
    }

    private fun finishMeasurement() {
        if (isCompleted) return
        isCompleted = true
        lockCameraExposure(false)

        val finalResult = if (validBpmReadings.isNotEmpty()) {
            val sorted = validBpmReadings.sorted()
            sorted[sorted.size / 2]
        } else {
            latestBpm
        }

        mainHandler.post {
            stopCameraOnly()
            if (finalResult in 45..175) {
                val beats15 = ((finalResult * 15.0) / 60.0).roundToInt()
                emitState(MeasurementState.Completed(finalResult))
                listener.onCompleted(finalResult, beats15)
            } else {
                isCompleted = false
                emitError("訊號不足，請將指腹同時蓋住前置鏡頭與綠光區後重測")
                emitState(MeasurementState.WaitingForFinger("請將指腹輕蓋住上方前置鏡頭與綠光區"))
                start()
            }
        }
    }

    private fun calculateCenterGreenAverage(imageProxy: ImageProxy): Double {
        val planes = imageProxy.planes
        if (planes.size < 3) return 0.0
        val yPlane = planes[0]
        val uPlane = planes[1]
        val vPlane = planes[2]

        val yBuffer = yPlane.buffer
        val uBuffer = uPlane.buffer
        val vBuffer = vPlane.buffer

        val width = imageProxy.width
        val height = imageProxy.height
        val yRowStride = yPlane.rowStride
        val uvRowStride = uPlane.rowStride
        val uvPixelStride = uPlane.pixelStride

        var greenSum = 0.0
        var pixelCount = 0

        val startX = width / 4
        val endX = width * 3 / 4
        val startY = height / 4
        val endY = height * 3 / 4

        for (y in startY until endY step 4) {
            for (x in startX until endX step 4) {
                val yIndex = y * yRowStride + x
                val uvIndex = (y / 2) * uvRowStride + (x / 2) * uvPixelStride

                if (yIndex < yBuffer.limit() &&
                    uvIndex < uBuffer.limit() &&
                    uvIndex < vBuffer.limit()
                ) {
                    val yVal = yBuffer.get(yIndex).toInt() and 0xFF
                    val uVal = (uBuffer.get(uvIndex).toInt() and 0xFF) - 128
                    val vVal = (vBuffer.get(uvIndex).toInt() and 0xFF) - 128

                    val g = yVal - 0.344136 * uVal - 0.714136 * vVal
                    greenSum += g.coerceIn(0.0, 255.0)
                    pixelCount++
                }
            }
        }
        return if (pixelCount > 0) greenSum / pixelCount else 0.0
    }

    private fun applyBandpassFilter(raw: Double): Double {
        val alphaHigh = 0.86
        val highPass = alphaHigh * (prevHighPass + raw - prevRaw)
        prevRaw = raw
        prevHighPass = highPass

        val alphaLow = 0.4
        val lowPass = prevLowPass + alphaLow * (highPass - prevLowPass)
        prevLowPass = lowPass

        return lowPass
    }

    private fun detectPeaksAndCalculateBpm() {
        val peaks = mutableListOf<Long>()
        val mean = signalBuffer.average()
        val stdDev = sqrt(signalBuffer.map { (it - mean) * (it - mean) }.average())
        val threshold = stdDev * 0.4

        for (i in 2 until signalBuffer.size - 2) {
            val curr = signalBuffer[i]
            if (curr > threshold &&
                curr > signalBuffer[i - 1] && curr > signalBuffer[i - 2] &&
                curr > signalBuffer[i + 1] && curr > signalBuffer[i + 2]
            ) {
                if (peaks.isEmpty() || (timeBuffer[i] - peaks.last() > 330)) {
                    peaks.add(timeBuffer[i])
                }
            }
        }

        if (peaks.size >= 4) {
            val durationMs = peaks.last() - peaks.first()
            val intervals = peaks.size - 1
            val avgInterval = durationMs.toDouble() / intervals
            val bpm = (60000.0 / avgInterval).toInt()

            if (bpm in 45..175) {
                latestBpm = bpm
                validBpmReadings.add(bpm)
            }
        }
    }

    private fun lockCameraExposure(lock: Boolean) {
        val control = cameraControl ?: return
        try {
            val camera2Control = Camera2CameraControl.from(control)
            val options = CaptureRequestOptions.Builder()
                .setCaptureRequestOption(CaptureRequest.CONTROL_AE_LOCK, lock)
                .setCaptureRequestOption(CaptureRequest.CONTROL_AWB_LOCK, lock)
                .setCaptureRequestOption(CaptureRequest.FLASH_MODE, CaptureRequest.FLASH_MODE_OFF)
                .build()
            camera2Control.setCaptureRequestOptions(options)
        } catch (_: Exception) {
        }
    }

    private fun resetInternalState() {
        isCompleted = false
        isExposureLocked = false
        measureStartTimeMs = null
        signalBuffer.clear()
        timeBuffer.clear()
        validBpmReadings.clear()
        latestBpm = 0
        prevRaw = 0.0
        prevHighPass = 0.0
        prevLowPass = 0.0
    }

    private fun stopCameraOnly() {
        try {
            cameraProvider?.unbindAll()
        } catch (_: Exception) {
        }
        camera = null
        cameraControl = null
    }

    private fun emitState(state: MeasurementState) {
        lastState = state
        mainHandler.post { listener.onState(state) }
    }

    private fun emitError(message: String) {
        mainHandler.post { listener.onError(message) }
    }

    companion object {
        private const val TAG = "FrontPPG"

        /** Build legacy 12-slot pulse_json from a front-camera green-fill BPM reading. */
        fun pulseJsonFromBpm(bpm: Int, beats15s: Int): org.json.JSONObject {
            val o = org.json.JSONObject()
            o.put("bpm", bpm)
            o.put("beats_15s", beats15s)
            o.put("method", "front_green_ppg")
            val slots = listOf(
                "left_cun_light", "left_cun_heavy",
                "left_guan_light", "left_guan_heavy",
                "left_chi_light", "left_chi_heavy",
                "right_cun_light", "right_cun_heavy",
                "right_guan_light", "right_guan_heavy",
                "right_chi_light", "right_chi_heavy",
            )
            for (s in slots) o.put(s, beats15s)
            return o
        }
    }
}
