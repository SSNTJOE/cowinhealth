package com.tube.healthing

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Outline
import android.os.Bundle
import android.view.View
import android.view.ViewOutlineProvider
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.tube.healthing.databinding.ActivityPulseBinding
import org.json.JSONObject
import java.time.LocalDate

/**
 * Front-camera green fill-light PPG pulse entry (Canvas UI).
 * Six 寸關尺 steps independently measurable; same-day last value kept per site.
 * Pulse organ analysis stays collapsed until user taps「脈搏分數」.
 * Wired from MainActivity「寸關尺／脈搏」. Does not replace login MainActivity.
 */
class PulseActivity : AppCompatActivity(), FrontCameraHeartRateMonitor.Listener {
    private lateinit var binding: ActivityPulseBinding
    private var monitor: FrontCameraHeartRateMonitor? = null
    private var lastBpm: Int? = null
    private var lastBeats15: Int? = null
    private var savedBrightness = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE
    private var positionIndex = 0
    private val stepChipButtons = mutableListOf<Button>()
    /** stepIndex → 15s beat count (for per-slot pulse_json + organ summary). */
    private val stepReadings = linkedMapOf<Int, Int>()
    private val stepBpms = linkedMapOf<Int, Int>()
    private var organExpanded = false
    private var pendingOrganSummary = ""

    private data class PulseStep(
        val stepKey: String,
        val heavyOrgan: String,
        val lightOrgan: String,
        val resId: Int,
    )

    private val steps = listOf(
        PulseStep("pulseStepLeftCun", "heart", "small_intestine", R.drawable.pulse_left_cun),
        PulseStep("pulseStepLeftGuan", "liver", "gallbladder", R.drawable.pulse_left_guan),
        PulseStep("pulseStepLeftChi", "kidney", "bladder", R.drawable.pulse_left_chi),
        PulseStep("pulseStepRightCun", "lung", "large_intestine", R.drawable.pulse_right_cun),
        PulseStep("pulseStepRightGuan", "spleen", "stomach", R.drawable.pulse_right_guan),
        PulseStep("pulseStepRightChi", "mingmen", "bladder", R.drawable.pulse_right_chi),
    )

    private fun uiLang(): String {
        val prefs = getSharedPreferences("healthing", MODE_PRIVATE)
        val stored = prefs.getString("ui_lang", "zh") ?: "zh"
        return if (stored in setOf("zh", "en", "ja", "ko")) stored else "zh"
    }

    private fun t(key: String): String = UiLang.t(uiLang(), key)

    private fun organName(key: String): String = UiLang.organName(uiLang(), key)

    private fun stepShortName(step: PulseStep): String = t(step.stepKey)

    private fun stepOrgansLabel(step: PulseStep): String =
        "${organName(step.heavyOrgan)}、${organName(step.lightOrgan)}"

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
            "前置鏡頭綠光補光 PPG（不開手電筒）\n" +
                "請用指腹同時蓋住上方前置鏡頭與純綠補光區。\n" +
                "上方可點選左／右 寸・關・尺：量完一格後留在本頁，再點其他格繼續量；不必一次量完六格。\n" +
                "今日讀值會保留，可稍後回來補量或重測；器官判定只看今日已量的穴位。\n" +
                "全部量完（或先量部分）再按一次「完成並回傳」。\n" +
                "螢幕亮度已調至最大；等待 → 自動量測 15 秒 → 完成（中位 BPM）。\n" +
                "15 秒次數＝BPM×15/60；>23 偏熱實，<14 偏寒虛。（教學示範，非診斷）"

        loadTodayReadings()
        inflateStepChips()
        selectPosition(firstOpenIndex(), armMonitor = false)
        showGuideImages(true)
        organExpanded = false
        refreshOrganConclusion()
        binding.pulseScoreToggle.setOnClickListener { toggleOrganConclusion() }

        binding.previewFrame.outlineProvider = object : ViewOutlineProvider() {
            override fun getOutline(view: View, outline: Outline) {
                outline.setOval(0, 0, view.width, view.height)
            }
        }
        binding.previewFrame.clipToOutline = true

        binding.start.setOnClickListener {
            // Clear only current-step draft; keep prior slot readings.
            lastBpm = null
            lastBeats15 = null
            binding.bpm.text = "— BPM"
            binding.done.isEnabled = stepReadings.isNotEmpty()
            binding.waveform.clear()
            binding.ring.setProgress(0f)
            applyMaxBrightness()
            ensureMonitor().remeasure()
        }
        binding.remeasure.setOnClickListener {
            lastBpm = null
            lastBeats15 = null
            stepReadings.remove(positionIndex)
            stepBpms.remove(positionIndex)
            saveTodayReadings()
            binding.bpm.text = "— BPM"
            binding.done.isEnabled = stepReadings.isNotEmpty()
            updateDoneLabel()
            binding.waveform.clear()
            binding.ring.setProgress(0f)
            refreshStepChips()
            refreshOrganConclusion()
            applyMaxBrightness()
            ensureMonitor().remeasure()
        }
        binding.done.setOnClickListener { finishWithResult() }

        // Bring action bar above any overlapping scroll content.
        binding.actionBar.bringToFront()
        binding.actionBar.elevation = 12f

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
        saveTodayReadings()
        monitor?.pause()
        super.onPause()
    }

    override fun onDestroy() {
        monitor?.stop()
        monitor = null
        restoreBrightness()
        super.onDestroy()
    }

    private fun prefs() = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    private fun todayKey(): String = "pulse_${LocalDate.now()}"

    private fun loadTodayReadings() {
        stepReadings.clear()
        stepBpms.clear()
        val raw = prefs().getString(todayKey(), null) ?: return
        try {
            val obj = JSONObject(raw)
            val beats = obj.optJSONObject("beats") ?: return
            val bpms = obj.optJSONObject("bpms")
            for (i in steps.indices) {
                val key = i.toString()
                if (!beats.has(key)) continue
                val b = beats.optInt(key, -1)
                if (b < 0) continue
                stepReadings[i] = b
                val bpm = bpms?.optInt(key, -1)?.takeIf { it > 0 } ?: ((b * 60) / 15)
                stepBpms[i] = bpm
            }
        } catch (_: Exception) {
            // Ignore corrupt prefs; start fresh for today.
        }
    }

    private fun saveTodayReadings() {
        val beats = JSONObject()
        val bpms = JSONObject()
        stepReadings.forEach { (i, b) ->
            beats.put(i.toString(), b)
            stepBpms[i]?.let { bpms.put(i.toString(), it) }
        }
        prefs().edit()
            .putString(todayKey(), JSONObject().put("beats", beats).put("bpms", bpms).toString())
            .apply()
    }

    private fun firstOpenIndex(): Int {
        for (i in steps.indices) {
            if (!stepReadings.containsKey(i)) return i
        }
        return 0
    }

    private fun inflateStepChips() {
        binding.stepChips.removeAllViews()
        stepChipButtons.clear()
        val padH = (8 * resources.displayMetrics.density).toInt()
        val padV = (4 * resources.displayMetrics.density).toInt()
        steps.forEachIndexed { index, step ->
            val btn = Button(this).apply {
                text = chipLabel(index, stepShortName(step))
                textSize = 12f
                isAllCaps = false
                setPadding(padH, padV, padH, padV)
                minimumHeight = 0
                minHeight = 0
                setOnClickListener { selectPosition(index) }
            }
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ).apply { marginEnd = padH }
            binding.stepChips.addView(btn, lp)
            stepChipButtons.add(btn)
        }
    }

    private fun chipLabel(index: Int, shortName: String): String {
        val bpm = stepBpms[index]
        return if (bpm != null) "${index + 1}.$shortName $bpm" else "${index + 1}.$shortName"
    }

    /**
     * Switch 寸關尺 site without leaving the screen.
     * [armMonitor]=true soft-resets PPG to Waiting so the newly selected site can be measured
     * immediately; does **not** clear other sites' same-day readings.
     */
    private fun selectPosition(index: Int, armMonitor: Boolean = true) {
        val next = index.coerceIn(0, steps.lastIndex)
        val switching = next != positionIndex
        positionIndex = next
        val step = steps[positionIndex]
        val shortName = stepShortName(step)
        val organs = stepOrgansLabel(step)
        val measuredCount = stepReadings.size
        binding.positionBanner.text =
            "目前量測：$shortName（$organs）· ${positionIndex + 1}／${steps.size}" +
                if (measuredCount > 0) " · 今日已量 $measuredCount 格" else ""
        binding.guideHand.setImageResource(step.resId)
        binding.guideCaption.text =
            "左：指腹蓋住綠光區與前置鏡頭｜右：紅圈＝$shortName（$organs）｜點上方穴位可換格繼續量"
        refreshStepChips()
        // Restore BPM display for this step if already measured.
        val priorBpm = stepBpms[positionIndex]
        val priorBeats = stepReadings[positionIndex]
        if (priorBpm != null && priorBeats != null) {
            lastBpm = priorBpm
            lastBeats15 = priorBeats
            binding.bpm.text = "$priorBpm BPM"
            binding.status.text =
                "已有今日讀值 $priorBpm BPM（15 秒約 $priorBeats 次）。可重測此格，或點其他穴位繼續量。"
        } else {
            lastBpm = null
            lastBeats15 = null
            binding.bpm.text = "— BPM"
            binding.status.text = "尚未量測 $shortName — 蓋住鏡頭後自動開始，或按開始偵測"
        }
        binding.done.isEnabled = stepReadings.isNotEmpty()
        updateDoneLabel()
        // Always keep 開始偵測 available so user can measure another site without leaving.
        binding.start.isEnabled = true
        binding.start.text = "開始偵測"
        binding.remeasure.isEnabled = true
        if (armMonitor && switching) {
            binding.waveform.clear()
            binding.ring.setProgress(0f)
            softArmMonitorForSite()
        }
    }

    private fun updateDoneLabel() {
        val n = stepReadings.size
        binding.done.text = when {
            n <= 0 -> "完成並回傳"
            n >= steps.size -> "完成並回傳（六格皆已量）"
            else -> "完成並回傳（今日已量 $n 格）"
        }
    }

    private fun refreshStepChips() {
        stepChipButtons.forEachIndexed { i, btn ->
            val selected = i == positionIndex
            val done = stepReadings.containsKey(i)
            btn.text = chipLabel(i, stepShortName(steps[i]))
            btn.setBackgroundColor(
                when {
                    selected -> Color.parseColor("#2E7D32")
                    done -> Color.parseColor("#455A64")
                    else -> Color.parseColor("#333333")
                }
            )
            btn.setTextColor(if (selected || done) Color.WHITE else Color.parseColor("#BDBDBD"))
        }
    }

    /** Reset PPG to Waiting for the current site; keep all saved same-day site readings. */
    private fun softArmMonitorForSite() {
        val m = monitor ?: return
        when (m.lastState) {
            is FrontCameraHeartRateMonitor.MeasurementState.Measuring,
            is FrontCameraHeartRateMonitor.MeasurementState.Completed,
            -> {
                if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
                    == PackageManager.PERMISSION_GRANTED
                ) {
                    m.remeasure()
                }
            }
            else -> Unit
        }
    }

    private fun applyMaxBrightness() {
        val lp = window.attributes
        if (savedBrightness == WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE ||
            savedBrightness < 0f
        ) {
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

    private fun toggleOrganConclusion() {
        if (pendingOrganSummary.isBlank()) {
            Toast.makeText(this, "先完成至少一格寸關尺量測", Toast.LENGTH_SHORT).show()
            return
        }
        organExpanded = !organExpanded
        applyOrganVisibility()
    }

    private fun applyOrganVisibility() {
        if (pendingOrganSummary.isBlank()) {
            binding.organConclusion.visibility = View.GONE
            binding.organConclusion.text = ""
            binding.pulseScoreToggle.text = "${t("pulseScoreToggle")} ▸"
            return
        }
        binding.pulseScoreToggle.text =
            if (organExpanded) "${t("pulseScoreToggle")} ▾" else "${t("pulseScoreToggle")} ▸"
        if (organExpanded) {
            binding.organConclusion.visibility = View.VISIBLE
            binding.organConclusion.text = pendingOrganSummary
        } else {
            binding.organConclusion.visibility = View.GONE
        }
    }

    private fun refreshOrganConclusion() {
        pendingOrganSummary = PulseOrganJudge.summaryFromReadings(
            stepReadings,
            organName = { organName(it) },
            title = t("pulseOrganSummaryTitle"),
        )
        // Stay collapsed by default; only show body when user already expanded.
        applyOrganVisibility()
    }

    private fun finishWithResult() {
        if (stepReadings.isEmpty()) {
            // Fallback: single last reading if map empty but lastBpm set.
            val bpm = lastBpm
            val beats = lastBeats15
            if (bpm == null || beats == null) {
                Toast.makeText(this, "尚無有效 BPM，請先完成量測", Toast.LENGTH_SHORT).show()
                return
            }
            stepReadings[positionIndex] = beats
            stepBpms[positionIndex] = bpm
        }
        saveTodayReadings()
        val json = PulseOrganJudge.pulseJsonFromReadings(
            stepReadings,
            lastBpm ?: stepBpms.values.lastOrNull(),
            organName = { organName(it) },
            title = t("pulseOrganSummaryTitle"),
        )
        val summary = json.optString("organ_summary")
        setResult(
            RESULT_OK,
            Intent()
                .putExtra("pulse_json", json.toString())
                .putExtra("organ_summary", summary),
        )
        finish()
    }

    private fun showGuideImages(visible: Boolean) {
        val v = if (visible) View.VISIBLE else View.GONE
        binding.guideImages.visibility = v
        binding.guideCaption.visibility = v
        if (visible) {
            binding.guideFinger.setImageResource(R.drawable.ppg_finger_guide)
            binding.guideHand.setImageResource(steps[positionIndex].resId)
        }
    }

    override fun onState(state: FrontCameraHeartRateMonitor.MeasurementState) {
        when (state) {
            is FrontCameraHeartRateMonitor.MeasurementState.WaitingForFinger -> {
                showGuideImages(true)
                binding.status.text = state.hint
                binding.start.isEnabled = true
                binding.start.text = "開始偵測"
                binding.remeasure.isEnabled = true
                binding.done.isEnabled = stepReadings.isNotEmpty() || lastBpm != null
            }
            is FrontCameraHeartRateMonitor.MeasurementState.Measuring -> {
                showGuideImages(true)
                val shortName = stepShortName(steps[positionIndex])
                binding.status.text =
                    if (state.currentBpm > 0) {
                        "量測 $shortName… ${state.remainingSeconds} 秒（約 ${state.currentBpm} BPM）"
                    } else {
                        "量測 $shortName… ${state.remainingSeconds} 秒"
                    }
                binding.ring.setProgress(state.progress)
                binding.start.isEnabled = false
                binding.start.text = "量測中… ${state.remainingSeconds} 秒"
                binding.remeasure.isEnabled = false
                // Keep 完成並回傳 available if other sites already have today's readings.
                binding.done.isEnabled = stepReadings.isNotEmpty()
                if (state.currentBpm > 0) {
                    binding.bpm.text = "${state.currentBpm} BPM"
                }
            }
            is FrontCameraHeartRateMonitor.MeasurementState.Completed -> {
                showGuideImages(true)
                // Stay on screen: start stays enabled so user can retest or switch chips next.
                binding.start.isEnabled = true
                binding.start.text = "開始偵測"
                binding.remeasure.isEnabled = true
                binding.done.isEnabled = stepReadings.isNotEmpty() || lastBpm != null
                binding.ring.setProgress(1f)
            }
        }
    }

    override fun onWaveUpdated(value: Float) {
        val norm = ((value / 8f) + 0.5f).coerceIn(0f, 1f)
        binding.waveform.push(norm)
    }

    override fun onCompleted(medianBpm: Int, beats15s: Int) {
        lastBpm = medianBpm
        lastBeats15 = beats15s
        stepReadings[positionIndex] = beats15s
        stepBpms[positionIndex] = medianBpm
        saveTodayReadings()
        val step = steps[positionIndex]
        val shortName = stepShortName(step)
        val lines = PulseOrganJudge.linesForStep(positionIndex, beats15s)
            .joinToString("；") { line ->
                PulseOrganJudge.shortLine(line) { key -> organName(key) }
            }
        val remaining = steps.size - stepReadings.size
        binding.done.isEnabled = true
        updateDoneLabel()
        binding.start.isEnabled = true
        binding.start.text = "開始偵測"
        binding.remeasure.isEnabled = true
        refreshOrganConclusion()
        // Refresh chips / banner; do not re-arm monitor (stay showing this result).
        selectPosition(positionIndex, armMonitor = false)
        binding.bpm.text = "$medianBpm BPM"
        binding.status.text =
            "完成 $shortName：中位 $medianBpm BPM（15 秒約 $beats15s 次）\n$lines\n" +
                if (remaining > 0) {
                    "可點上方其他穴位繼續量（今日已量 ${stepReadings.size}／${steps.size}），或按完成並回傳。"
                } else {
                    "六格皆已有今日讀值；可重測任一格，或按完成並回傳。"
                }
        Toast.makeText(
            this,
            if (remaining > 0) {
                "$shortName $medianBpm BPM｜點其他穴位可繼續量"
            } else {
                "$shortName $medianBpm BPM｜可完成並回傳"
            },
            Toast.LENGTH_LONG,
        ).show()
    }

    override fun onError(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        binding.start.isEnabled = true
        binding.remeasure.isEnabled = true
    }

    companion object {
        private const val PREFS_NAME = "pulse_day_sites"
    }
}
