package com.tube.healthing

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Outline
import android.os.Bundle
import android.view.View
import android.view.ViewOutlineProvider
import android.view.WindowManager
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.tube.healthing.databinding.ActivityPulseBinding

/**
 * Front-camera green fill-light PPG pulse entry (Canvas UI).
 * Wired from MainActivity「寸關尺／脈搏」. Does not replace login MainActivity.
 */
class PulseActivity : AppCompatActivity(), FrontCameraHeartRateMonitor.Listener {
    private lateinit var binding: ActivityPulseBinding
    private var monitor: FrontCameraHeartRateMonitor? = null
    private var lastBpm: Int? = null
    private var lastBeats15: Int? = null
    private var savedBrightness = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE

    private val permission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            applyMaxBrightness()
            ensureMonitor().start()
        } else {
            Toast.makeText(this, "脈診需要相機權限（前置鏡頭）", Toast.LENGTH_LONG).show()
            finish()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPulseBinding.inflate(layoutInflater)
        setContentView(binding.root)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        applyMaxBrightness()

        binding.guide.text =
            "前置鏡頭綠光補光 PPG\n" +
                "請用指腹同時蓋住上方前置鏡頭與純綠補光區（不開手電筒）。\n" +
                "螢幕亮度已調至最大；等待 → 自動量測 15 秒 → 完成（中位 BPM）。\n" +
                "15 秒次數＝BPM×15/60；>23 偏熱實，<14 偏寒虛。（教學示範，非診斷）"

        // Show placement guides while waiting / measuring (寸關尺 demos + finger PPG).
        showGuideImages(true)
        binding.guideHand.setOnClickListener { cycleHandGuide() }

        binding.previewFrame.outlineProvider = object : ViewOutlineProvider() {
            override fun getOutline(view: View, outline: Outline) {
                outline.setOval(0, 0, view.width, view.height)
            }
        }
        binding.previewFrame.clipToOutline = true

        binding.start.setOnClickListener {
            lastBpm = null
            lastBeats15 = null
            binding.bpm.text = "— BPM"
            binding.done.isEnabled = false
            binding.waveform.clear()
            binding.ring.setProgress(0f)
            applyMaxBrightness()
            ensureMonitor().remeasure()
        }
        binding.remeasure.setOnClickListener {
            lastBpm = null
            lastBeats15 = null
            binding.bpm.text = "— BPM"
            binding.done.isEnabled = false
            binding.waveform.clear()
            binding.ring.setProgress(0f)
            applyMaxBrightness()
            ensureMonitor().remeasure()
        }
        binding.done.setOnClickListener { finishWithResult() }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED
        ) {
            permission.launch(Manifest.permission.CAMERA)
        }
    }

    override fun onResume() {
        super.onResume()
        applyMaxBrightness()
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED
        ) {
            val m = ensureMonitor()
            if (m.lastState !is FrontCameraHeartRateMonitor.MeasurementState.Completed) {
                m.start()
            }
        }
    }

    override fun onPause() {
        monitor?.pause()
        super.onPause()
    }

    override fun onDestroy() {
        monitor?.stop()
        monitor = null
        restoreBrightness()
        super.onDestroy()
    }

    private fun applyMaxBrightness() {
        val lp = window.attributes
        if (savedBrightness == WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE ||
            savedBrightness < 0f
        ) {
            // Keep first non-max value so we can restore later.
            if (lp.screenBrightness in 0f..0.99f) {
                savedBrightness = lp.screenBrightness
            }
        }
        lp.screenBrightness = 1f
        window.attributes = lp
    }

    private fun restoreBrightness() {
        val lp = window.attributes
        lp.screenBrightness = if (savedBrightness >= 0f) {
            savedBrightness
        } else {
            WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE
        }
        window.attributes = lp
    }

    private fun ensureMonitor(): FrontCameraHeartRateMonitor {
        val existing = monitor
        if (existing != null) return existing
        val created = FrontCameraHeartRateMonitor(this, this, binding.preview, this)
        monitor = created
        return created
    }

    private fun finishWithResult() {
        val bpm = lastBpm
        val beats = lastBeats15
        if (bpm == null || beats == null) {
            Toast.makeText(this, "尚無有效 BPM，請先完成量測", Toast.LENGTH_SHORT).show()
            return
        }
        val json = FrontCameraHeartRateMonitor.pulseJsonFromBpm(bpm, beats)
        setResult(RESULT_OK, Intent().putExtra("pulse_json", json.toString()))
        finish()
    }

    private val handGuideRes = intArrayOf(
        R.drawable.pulse_hand,
        R.drawable.pulse_left_cun,
        R.drawable.pulse_left_guan,
        R.drawable.pulse_left_chi,
        R.drawable.pulse_right_cun,
        R.drawable.pulse_right_guan,
        R.drawable.pulse_right_chi,
    )
    private var handGuideIndex = 0

    private fun showGuideImages(visible: Boolean) {
        val v = if (visible) View.VISIBLE else View.GONE
        binding.guideImages.visibility = v
        binding.guideCaption.visibility = v
        if (visible) {
            binding.guideFinger.setImageResource(R.drawable.ppg_finger_guide)
            binding.guideHand.setImageResource(handGuideRes[handGuideIndex])
        }
    }

    private fun cycleHandGuide() {
        handGuideIndex = (handGuideIndex + 1) % handGuideRes.size
        binding.guideHand.setImageResource(handGuideRes[handGuideIndex])
    }

    override fun onState(state: FrontCameraHeartRateMonitor.MeasurementState) {
        when (state) {
            is FrontCameraHeartRateMonitor.MeasurementState.WaitingForFinger -> {
                showGuideImages(true)
                binding.status.text = state.hint
                binding.start.isEnabled = true
                binding.start.text = "開始偵測"
                binding.remeasure.isEnabled = true
                binding.done.isEnabled = lastBpm != null
            }
            is FrontCameraHeartRateMonitor.MeasurementState.Measuring -> {
                showGuideImages(true)
                binding.status.text =
                    if (state.currentBpm > 0) {
                        "量測中… ${state.remainingSeconds} 秒（約 ${state.currentBpm} BPM）"
                    } else {
                        "量測中… ${state.remainingSeconds} 秒"
                    }
                binding.ring.setProgress(state.progress)
                binding.start.isEnabled = false
                binding.start.text = "量測中… ${state.remainingSeconds} 秒"
                binding.remeasure.isEnabled = false
                binding.done.isEnabled = false
                if (state.currentBpm > 0) {
                    binding.bpm.text = "${state.currentBpm} BPM"
                }
            }
            is FrontCameraHeartRateMonitor.MeasurementState.Completed -> {
                showGuideImages(false)
                binding.status.text = "完成"
                binding.start.isEnabled = false
                binding.remeasure.isEnabled = true
                binding.done.isEnabled = lastBpm != null
                binding.ring.setProgress(1f)
            }
        }
    }

    override fun onWaveUpdated(value: Float) {
        // Normalize loosely for waveform display (bandpass centered near 0).
        val norm = ((value / 8f) + 0.5f).coerceIn(0f, 1f)
        binding.waveform.push(norm)
    }

    override fun onCompleted(medianBpm: Int, beats15s: Int) {
        lastBpm = medianBpm
        lastBeats15 = beats15s
        binding.bpm.text = "$medianBpm BPM"
        binding.status.text = "完成：中位 $medianBpm BPM（15 秒約 $beats15s 次）"
        binding.done.isEnabled = true
        binding.remeasure.isEnabled = true
        Toast.makeText(this, "脈搏 $medianBpm BPM", Toast.LENGTH_SHORT).show()
    }

    override fun onError(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        binding.start.isEnabled = true
        binding.remeasure.isEnabled = true
    }
}
