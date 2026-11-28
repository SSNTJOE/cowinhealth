package com.tube.healthing

import org.json.JSONObject

/**
 * Teaching-demo pulse → 五臟六腑 short conclusions.
 * Mirrors server [app/syndrome.py] `PULSE_TO_ORGAN` + `apply_pulse` + `overlay_from_weights`.
 * Thresholds: 15s beats >23 → 熱實；<14 → 寒虛.（同 PulseActivity 導引文案）
 */
object PulseOrganJudge {
    data class SlotOrgans(
        val lightKey: String,
        val heavyKey: String,
        val lightOrgan: String,
        val heavyOrgan: String,
    )

    /** Six 寸關尺 steps → light/heavy slots (same map as syndrome.PULSE_TO_ORGAN). */
    val STEP_SLOTS = listOf(
        SlotOrgans("left_cun_light", "left_cun_heavy", "small_intestine", "heart"),
        SlotOrgans("left_guan_light", "left_guan_heavy", "gallbladder", "liver"),
        SlotOrgans("left_chi_light", "left_chi_heavy", "bladder", "kidney"),
        SlotOrgans("right_cun_light", "right_cun_heavy", "large_intestine", "lung"),
        SlotOrgans("right_guan_light", "right_guan_heavy", "stomach", "spleen"),
        // Right chi heavy maps to kidney / mingmen teaching label.
        SlotOrgans("right_chi_light", "right_chi_heavy", "bladder", "mingmen"),
    )

    data class OrganLine(
        val organKey: String,
        val pattern: String,
        val score: Int,
        val note: String,
    )

    /** Same weights as syndrome.apply_pulse when count >23 or <14. */
    fun judgeBeats(beats15s: Int): Triple<String, Int, String> {
        return when {
            beats15s > 23 -> {
                // 熱證 1.8 + 實證 1.4 → overlay_from_weights → 實證熱證, score≈3
                val (label, score) = overlayFromWeights(xu = 0.0, shi = 1.4, re = 1.8, han = 0.0)
                Triple(label, score, "數脈偏熱實")
            }
            beats15s < 14 -> {
                val (label, score) = overlayFromWeights(xu = 1.4, shi = 0.0, re = 0.0, han = 1.8)
                Triple(label, score, "遲脈偏寒虛")
            }
            else -> Triple("待觀察", 5, "脈率接近平常")
        }
    }

    /** Port of syndrome.overlay_from_weights (pattern + 1–10 score). */
    fun overlayFromWeights(xu: Double, shi: Double, re: Double, han: Double): Pair<String, Int> {
        val strongest = maxOf(xu, shi, re, han)
        if (strongest < 0.9) return "待觀察" to 5
        var xuShi = if (xu >= shi) "虛證" else "實證"
        val xsW = if (xu >= shi) xu else shi
        var reHan = if (re >= han) "熱證" else "寒證"
        val rhW = if (re >= han) re else han
        if (xsW < 0.9) xuShi = if (reHan == "熱證") "實證" else "虛證"
        if (rhW < 0.9) reHan = if (xuShi == "實證") "熱證" else "寒證"
        val label = "$xuShi$reHan"
        val score = maxOf(1, minOf(10, kotlin.math.round(5.0 - minOf(strongest, 4.0)).toInt()))
        return label to score
    }

    fun linesForStep(stepIndex: Int, beats15s: Int): List<OrganLine> {
        val slot = STEP_SLOTS.getOrNull(stepIndex) ?: return emptyList()
        val (pattern, score, note) = judgeBeats(beats15s)
        // PPG cannot split light/heavy pressure; both paired organs share the same reading
        // (same as FrontCameraHeartRateMonitor.pulseJsonFromBpm filling both slots).
        return listOf(
            OrganLine(slot.heavyOrgan, pattern, score, note),
            OrganLine(slot.lightOrgan, pattern, score, note),
        )
    }

    fun shortLine(line: OrganLine, organName: (String) -> String): String {
        val display = when {
            line.score >= 8 -> "健康"
            line.pattern == "待觀察" -> "待觀察"
            else -> line.pattern
        }
        return "${organName(line.organKey)}：$display（${line.note}，約${line.score}分）"
    }

    fun summaryFromReadings(
        readings: Map<Int, Int>,
        organName: (String) -> String = { UiLang.organName("zh", it) },
        title: String = UiLang.t("zh", "pulseOrganSummaryTitle"),
    ): String {
        if (readings.isEmpty()) return ""
        val byOrgan = LinkedHashMap<String, OrganLine>()
        readings.toSortedMap().forEach { (step, beats) ->
            linesForStep(step, beats).forEach { line ->
                val prev = byOrgan[line.organKey]
                // Keep the more severe (lower) score when 右尺 overlaps 腎／膀胱.
                if (prev == null || line.score < prev.score) {
                    byOrgan[line.organKey] = line
                }
            }
        }
        val body = byOrgan.values.joinToString("\n") { shortLine(it, organName) }
        return "$title\n$body"
    }

    /** Build 12-slot pulse_json from per-step 15s beat counts. */
    fun pulseJsonFromReadings(
        readings: Map<Int, Int>,
        lastBpm: Int?,
        method: String = "front_green_ppg",
        organName: (String) -> String = { UiLang.organName("zh", it) },
        title: String = UiLang.t("zh", "pulseOrganSummaryTitle"),
    ): JSONObject {
        val o = JSONObject()
        o.put("method", method)
        if (lastBpm != null) o.put("bpm", lastBpm)
        readings.values.firstOrNull()?.let { o.put("beats_15s", it) }
        STEP_SLOTS.forEachIndexed { index, slot ->
            val beats = readings[index]
            if (beats != null) {
                o.put(slot.lightKey, beats)
                o.put(slot.heavyKey, beats)
            }
        }
        // Conclusions for UI / logging (server ignores unknown keys).
        o.put("organ_summary", summaryFromReadings(readings, organName, title))
        return o
    }
}
