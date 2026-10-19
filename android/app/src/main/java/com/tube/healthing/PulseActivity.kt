package com.tube.healthing

import android.content.Intent
import android.os.Bundle
import android.os.CountDownTimer
import android.util.Size
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import com.tube.healthing.databinding.ActivityPulseBinding
import org.json.JSONObject
import java.util.concurrent.Executors
import kotlin.math.abs

class PulseActivity : AppCompatActivity() {
    private lateinit var binding: ActivityPulseBinding
    private val executor = Executors.newSingleThreadExecutor()
    private var camera: Camera? = null
    private val results = JSONObject()
    private var beats = 0
    private var lastLuma = 0.0
    private var lastBeatAt = 0L
    private var measuring = false
    private var step = 0

    private val steps = listOf(
        Triple("left_cun_light", "左手寸、輕按（小腸）", "請把後置鏡頭與 LED 貼在左手寸部，先輕放。"),
        Triple("left_cun_heavy", "左手寸、重按（心）", "同一位置稍微用力下壓。"),
        Triple("left_guan_light", "左手關、輕按（膽）", "移到左手關部，先輕放。"),
        Triple("left_guan_heavy", "左手關、重按（肝）", "關部加重。"),
        Triple("left_chi_light", "左手尺、輕按（膀胱）", "左手尺部輕放。"),
        Triple("left_chi_heavy", "左手尺、重按（腎）", "尺部加重。"),
        Triple("right_cun_light", "右手寸、輕按（大腸）", "換成右手寸部輕放。"),
        Triple("right_cun_heavy", "右手寸、重按（肺）", "右手寸部加重。"),
        Triple("right_guan_light", "右手關、輕按（胃）", "右手關部輕放。"),
        Triple("right_guan_heavy", "右手關、重按（脾）", "右手關部加重。"),
        Triple("right_chi_light", "右手尺、輕按（三焦）", "右手尺部輕放。"),
        Triple("right_chi_heavy", "右手尺、重按（心包）", "右手尺部加重。"),
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPulseBinding.inflate(layoutInflater)
        setContentView(binding.root)
        showStep()
        startCamera()
        binding.start.setOnClickListener { startMeasure() }
    }

    private fun showStep() {
        val item = steps[step]
        binding.guide.text = "步驟 ${step + 1}/12\n${item.second}\n${item.third}\n後置鏡頭會打開 LED。把鏡頭貼在該側手腕的寸、關或尺上。15 秒超過 23 次為熱/實，少於 14 次為寒/虛。"
        binding.count.text = "0 次"
    }

    private fun startCamera() {
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            binding.preview.implementationMode = PreviewView.ImplementationMode.COMPATIBLE
            val provider = future.get()
            val preview = Preview.Builder()
                .setResolutionSelector(
                    ResolutionSelector.Builder()
                        .setResolutionStrategy(
                            ResolutionStrategy(
                                Size(1280, 720),
                                ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER
                            )
                        )
                        .build()
                )
                .build()
                .also { it.setSurfaceProvider(binding.preview.surfaceProvider) }
            val analysis = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
            analysis.setAnalyzer(executor) { image ->
                if (measuring) {
                    val plane = image.planes[0]
                    val buffer = plane.buffer
                    val data = ByteArray(buffer.remaining())
                    buffer.get(data)
                    var sum = 0L
                    for (b in data) sum += (b.toInt() and 0xFF)
                    val luma = sum.toDouble() / data.size
                    val now = System.currentTimeMillis()
                    if (abs(luma - lastLuma) > 4 && now - lastBeatAt > 280) {
                        beats += 1
                        lastBeatAt = now
                        runOnUiThread { binding.count.text = "$beats 次" }
                    }
                    lastLuma = luma
                }
                image.close()
            }
            provider.unbindAll()
            val bound = provider.bindToLifecycle(
                this,
                CameraSelector.DEFAULT_BACK_CAMERA,
                preview,
                analysis
            )
            camera = bound
            if (bound.cameraInfo.hasFlashUnit()) {
                bound.cameraControl.enableTorch(true)
            }
        }, ContextCompat.getMainExecutor(this))
    }

    override fun onDestroy() {
        camera?.cameraControl?.enableTorch(false)
        executor.shutdown()
        super.onDestroy()
    }

    private fun startMeasure() {
        if (measuring) return
        beats = 0
        measuring = true
        binding.start.isEnabled = false
        object : CountDownTimer(15_000, 1000) {
            override fun onTick(millisUntilFinished: Long) {
                binding.start.text = "量測中… ${(millisUntilFinished / 1000)} 秒"
            }
            override fun onFinish() {
                measuring = false
                results.put(steps[step].first, beats)
                Toast.makeText(this@PulseActivity, "本段 $beats 次", Toast.LENGTH_SHORT).show()
                step += 1
                if (step >= steps.size) {
                    setResult(RESULT_OK, Intent().putExtra("pulse_json", results.toString()))
                    finish()
                } else {
                    binding.start.isEnabled = true
                    binding.start.text = "開始 15 秒"
                    showStep()
                }
            }
        }.start()
    }
}
