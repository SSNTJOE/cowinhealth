package com.tube.healthing

import java.util.Locale
import kotlin.math.floor

/** Taiwan HPA adult BMI cutoffs, matching app/static/common.js. */
object Bmi {
    private const val HEALTHY_BMI_MIN = 18.5
    private const val HEALTHY_BMI_MAX = 24.0
    private const val HEALTHY_BMI_MAX_DISPLAY = 23.9

    fun parsePositiveNumber(value: String?): Double? {
        val n = value?.trim()?.toDoubleOrNull() ?: return null
        return if (n.isFinite() && n > 0.0) n else null
    }

    fun compute(heightCm: String?, weightKg: String?): Double? {
        val height = parsePositiveNumber(heightCm) ?: return null
        val weight = parsePositiveNumber(weightKg) ?: return null
        val meters = height / 100.0
        if (meters <= 0.0) return null
        return weight / (meters * meters)
    }

    fun categoryTw(bmi: Double?): String {
        if (bmi == null || !bmi.isFinite()) return ""
        return when {
            bmi < 18.5 -> "過輕"
            bmi < 24.0 -> "健康體重"
            bmi < 27.0 -> "過重"
            bmi < 30.0 -> "輕度肥胖"
            bmi < 35.0 -> "中度肥胖"
            else -> "重度肥胖"
        }
    }

    fun healthyWeightRangeKg(heightCm: String?): Pair<Double, Double>? {
        val height = parsePositiveNumber(heightCm) ?: return null
        val h2 = (height * height) / 10000.0
        val minKg = jsRound(HEALTHY_BMI_MIN * h2 * 10.0) / 10.0
        val exclusiveKg = HEALTHY_BMI_MAX * h2
        val maxKg = jsRound((floor(exclusiveKg * 10.0 + 1e-8) / 10.0 - 0.1) * 10.0) / 10.0
        if (!(minKg > 0.0) || !(maxKg >= minKg)) return null
        return minKg to maxKg
    }

    fun formatHealthyReference(heightCm: String?): String {
        val range = healthyWeightRangeKg(heightCm) ?: return ""
        return "參考：BMI " +
            oneDecimal(HEALTHY_BMI_MIN) +
            "–" +
            oneDecimal(HEALTHY_BMI_MAX_DISPLAY) +
            "，建議體重 " +
            oneDecimal(range.first) +
            "–" +
            oneDecimal(range.second) +
            " kg"
    }

    fun formatDisplay(heightCm: String?, weightKg: String?): String {
        parsePositiveNumber(heightCm) ?: return ""
        val ref = formatHealthyReference(heightCm)
        val bmi = compute(heightCm, weightKg) ?: return ""
        val line = "BMI " + oneDecimal(bmi) + "（" + categoryTw(bmi) + "）"
        return if (ref.isNotEmpty()) line + "　" + ref else line
    }

    /** Match JavaScript Math.round for positive values (half toward +Infinity). */
    private fun jsRound(value: Double): Double = floor(value + 0.5)

    private fun oneDecimal(value: Double): String = String.format(Locale.US, "%.1f", value)
}
