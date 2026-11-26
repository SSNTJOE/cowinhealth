package com.tube.healthing

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.util.TypedValue
import android.view.Gravity
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.GridLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject

data class OrganSpot(val key: String, val name: String, val x: Float, val y: Float, val femaleOnly: Boolean = false)

data class OrganScoreMeta(
    val key: String,
    val name: String,
    val scoreKey: String,
    val patternKey: String,
    val femaleOnly: Boolean = false,
)

val ORGAN_SPOTS = listOf(
    OrganSpot("lung", "肺", 0.44f, 0.315f),
    OrganSpot("lung", "肺", 0.56f, 0.315f),
    OrganSpot("heart", "心", 0.535f, 0.355f),
    OrganSpot("liver", "肝", 0.44f, 0.415f),
    OrganSpot("gallbladder", "膽", 0.415f, 0.445f),
    OrganSpot("spleen", "脾", 0.565f, 0.435f),
    OrganSpot("stomach", "胃", 0.60f, 0.48f),
    OrganSpot("large_intestine", "大腸", 0.38f, 0.52f),
    OrganSpot("large_intestine", "大腸", 0.62f, 0.52f),
    OrganSpot("small_intestine", "小腸", 0.50f, 0.54f),
    OrganSpot("kidney", "腎", 0.44f, 0.61f),
    OrganSpot("kidney", "腎", 0.56f, 0.61f),
    OrganSpot("bladder", "膀胱", 0.50f, 0.645f),
    OrganSpot("uterus", "子宮", 0.50f, 0.625f, femaleOnly = true),
)

/** Same organ order as web score cards (measured-only averages from server). */
val ORGAN_SCORE_META = listOf(
    OrganScoreMeta("heart", "心", "heart_score", "heart_pattern"),
    OrganScoreMeta("liver", "肝", "liver_score", "liver_pattern"),
    OrganScoreMeta("spleen", "脾", "spleen_score", "spleen_pattern"),
    OrganScoreMeta("stomach", "胃", "stomach_score", "stomach_pattern"),
    OrganScoreMeta("lung", "肺", "lung_score", "lung_pattern"),
    OrganScoreMeta("kidney", "腎", "kidney_score", "kidney_pattern"),
    OrganScoreMeta("gallbladder", "膽", "gallbladder_score", "gallbladder_pattern"),
    OrganScoreMeta("large_intestine", "大腸", "large_intestine_score", "large_intestine_pattern"),
    OrganScoreMeta("small_intestine", "小腸", "small_intestine_score", "small_intestine_pattern"),
    OrganScoreMeta("bladder", "膀胱", "bladder_score", "bladder_pattern"),
    OrganScoreMeta("uterus", "子宮", "uterus_score", "uterus_pattern", femaleOnly = true),
)

val SYNDROME_LEGEND = listOf(
    "strong-hot.png" to "legendStrongHot",
    "strong-cold.png" to "legendStrongCold",
    "weak-hot.png" to "legendWeakHot",
    "weak-cold.png" to "legendWeakCold",
    "mositure.png" to "legendMoisture",
)

private val SYNDROME_STICKERS = setOf(
    "strong-hot.png",
    "strong-cold.png",
    "weak-hot.png",
    "weak-cold.png",
    "mositure.png",
)

private val MEDIA_ALIASES = mapOf(
    "moisture.png" to "mositure.png",
    "week-hot.png" to "weak-hot.png",
    "week-cold.png" to "weak-cold.png",
)

/** Alpha for the four syndrome stickers. Null hides 8–10, which count as healthy. */
fun syndromeStickerAlpha(file: String, score: Int?): Float? {
    if (file !in SYNDROME_STICKERS) return 1f
    val n = score ?: return 1f
    if (n >= 8) return null
    val transparency = when (n.coerceIn(1, 7)) {
        1 -> 0f
        2 -> 0.2f
        3 -> 0.4f
        4 -> 0.5f
        5 -> 0.6f
        6 -> 0.7f
        else -> 0.8f
    }
    return 1f - transparency
}

/**
 * Decode a media PNG: bundled `assets/media/` first (always works offline),
 * then `$baseUrl/media/` when the server is configured — same paths as the website.
 */
fun decodeMediaBitmap(
    context: Context,
    name: String,
    mediaUrl: (String) -> String,
    client: OkHttpClient
): Bitmap? {
    val wanted = MEDIA_ALIASES[name] ?: name
    for (candidate in listOf(wanted, name).distinct()) {
        try {
            context.assets.open("media/$candidate").use { stream ->
                BitmapFactory.decodeStream(stream)?.let { return it }
            }
        } catch (_: Exception) {
        }
    }
    for (candidate in listOf(wanted, name).distinct()) {
        try {
            val url = mediaUrl(candidate)
            if (!url.startsWith("http://") && !url.startsWith("https://")) continue
            val req = Request.Builder().url(url).build()
            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) return@use
                val bytes = resp.body?.bytes() ?: return@use
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.let { return it }
            }
        } catch (_: Exception) {
        }
    }
    return null
}

fun applyBodyOverlays(
    container: FrameLayout,
    bodyView: ImageView,
    overlays: JSONObject?,
    scores: JSONObject?,
    female: Boolean,
    mediaUrl: (String) -> String,
    client: OkHttpClient
) {
    fun clearPins() {
        val toRemove = mutableListOf<android.view.View>()
        for (i in 0 until container.childCount) {
            val child = container.getChildAt(i)
            if (child !== bodyView) toRemove.add(child)
        }
        toRemove.forEach { container.removeView(it) }
    }

    if (overlays == null) {
        bodyView.post { clearPins() }
        return
    }

    // Decode stickers off the UI thread, then place on UI thread (same overlay keys as web).
    val decoded = mutableListOf<Triple<OrganSpot, Bitmap, Float>>()
    ORGAN_SPOTS.forEach { spot ->
        if (spot.femaleOnly && !female) return@forEach
        val file = overlays.optString(spot.key, "")
        if (file.isBlank() || file == "null") return@forEach
        val score = scores?.optInt(spot.key + "_score", -1) ?: -1
        val alpha = syndromeStickerAlpha(file, if (score < 0) null else score) ?: return@forEach
        val bmp = decodeMediaBitmap(container.context, file, mediaUrl, client) ?: return@forEach
        decoded.add(Triple(spot, bmp, alpha))
    }

    fun place() {
        val w = bodyView.width
        val h = bodyView.height
        if (w == 0 || h == 0) {
            bodyView.post { place() }
            return
        }
        clearPins()
        val ctx = container.context
        decoded.forEach { (spot, bmp, alpha) ->
            val size = (w * 0.13f).toInt().coerceAtLeast(24)
            val img = ImageView(ctx)
            img.setImageBitmap(bmp)
            img.adjustViewBounds = true
            img.alpha = alpha
            img.setBackgroundColor(Color.TRANSPARENT)
            val lp = FrameLayout.LayoutParams(size, size)
            img.x = w * spot.x - size / 2f
            img.y = h * spot.y - size / 2f
            container.addView(img, lp)
            val label = TextView(ctx)
            label.text = spot.name
            label.textSize = 10f
            label.x = w * spot.x - 20
            label.y = h * spot.y + size / 3f
            container.addView(
                label,
                ViewGroup.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT
                )
            )
        }
    }
    bodyView.post { place() }
}

/** Syndrome schematic legend (same five stickers as the website). */
fun bindSyndromeLegend(
    row: LinearLayout,
    mediaUrl: (String) -> String,
    client: OkHttpClient,
    labelOf: (String) -> String,
) {
    val ctx = row.context
    Thread {
        val items = SYNDROME_LEGEND.mapNotNull { (file, key) ->
            val bmp = decodeMediaBitmap(ctx, file, mediaUrl, client) ?: return@mapNotNull null
            Triple(bmp, labelOf(key), file)
        }
        row.post {
            row.removeAllViews()
            val pad = TypedValue.applyDimension(
                TypedValue.COMPLEX_UNIT_DIP, 6f, ctx.resources.displayMetrics
            ).toInt()
            val icon = TypedValue.applyDimension(
                TypedValue.COMPLEX_UNIT_DIP, 28f, ctx.resources.displayMetrics
            ).toInt()
            items.forEach { (bmp, label, _) ->
                val cell = LinearLayout(ctx).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    setPadding(pad, pad / 2, pad, pad / 2)
                }
                val img = ImageView(ctx).apply {
                    setImageBitmap(bmp)
                    layoutParams = LinearLayout.LayoutParams(icon, icon)
                    adjustViewBounds = true
                }
                val tv = TextView(ctx).apply {
                    text = label
                    textSize = 12f
                    setPadding(pad / 2, 0, 0, 0)
                }
                cell.addView(img)
                cell.addView(tv)
                row.addView(cell)
            }
        }
    }.start()
}

fun patternDisplayLabel(score: Int?, pattern: String?): String {
    val n = score ?: return pattern.orEmpty()
    if (n >= 8) return "健康"
    if (n == 5 && (pattern.isNullOrBlank() || pattern == "未定")) return "待觀察"
    return pattern.orEmpty()
}

/** Bind per-organ average scores (server averages measured modalities only). */
fun bindOrganScores(
    grid: GridLayout,
    scores: JSONObject?,
    patterns: JSONObject?,
    female: Boolean,
    organLabel: (String) -> String = { key ->
        ORGAN_SCORE_META.firstOrNull { it.key == key }?.name ?: key
    },
) {
    grid.removeAllViews()
    val ctx = grid.context
    ORGAN_SCORE_META.forEach { meta ->
        if (meta.femaleOnly && !female) return@forEach
        val score = when {
            scores == null -> null
            scores.has(meta.scoreKey) -> scores.optInt(meta.scoreKey, -1).takeIf { it >= 0 }
            else -> null
        }
        val rawPattern = patterns?.optString(meta.patternKey).orEmpty()
        val pattern = patternDisplayLabel(score, rawPattern)
        val cell = LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(8, 8, 8, 8)
            setBackgroundColor(Color.parseColor("#F5F5F5"))
        }
        cell.addView(TextView(ctx).apply {
            text = organLabel(meta.key)
            textSize = 12f
            setTextColor(Color.parseColor("#616161"))
        })
        cell.addView(TextView(ctx).apply {
            text = score?.toString() ?: "—"
            textSize = 18f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        })
        if (pattern.isNotBlank()) {
            cell.addView(TextView(ctx).apply {
                text = pattern
                textSize = 11f
                setTextColor(Color.parseColor("#424242"))
            })
        }
        val lp = GridLayout.LayoutParams().apply {
            width = 0
            height = ViewGroup.LayoutParams.WRAP_CONTENT
            columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f)
            setMargins(4, 4, 4, 4)
        }
        grid.addView(cell, lp)
    }
}

/**
 * Build a short Traditional-Chinese-friendly session summary for today’s reading.
 * Uses measured-only organ averages + findings (teaching demo, not diagnosis).
 */
fun buildSessionSummary(
    json: JSONObject,
    female: Boolean,
    headingIdle: String,
    sourceLabelOf: (String) -> String,
    organLabel: (String) -> String = { key ->
        ORGAN_SCORE_META.firstOrNull { it.key == key }?.name ?: key
    },
    organScoresHeading: String = "臟腑平均分（僅有測到的來源）",
): String {
    val scores = json.optJSONObject("scores")
    val patterns = json.optJSONObject("patterns")
    if (scores == null && patterns == null && json.optJSONArray("findings") == null) {
        return headingIdle
    }
    val lines = mutableListOf<String>()
    lines.add("教學示範，非診斷。")

    val health = json.optJSONObject("organ_health")
    val sourceKeys = health?.optJSONArray("source_keys")
    if (sourceKeys != null && sourceKeys.length() > 0) {
        val names = (0 until sourceKeys.length()).mapNotNull { i ->
            sourceLabelOf(sourceKeys.optString(i))
        }
        if (names.isNotEmpty()) {
            lines.add("本場有測來源：" + names.joinToString("、"))
        }
    }

    // Separate short stool / urine lines: normal vs notes of concern.
    for (kind in listOf("stool", "urine")) {
        if (StoolUrineJudge.noteForKind(json, kind) != null) {
            lines.add(StoolUrineJudge.briefStatus(json, kind))
        }
    }

    val scored = ORGAN_SCORE_META.mapNotNull { meta ->
        if (meta.femaleOnly && !female) return@mapNotNull null
        if (scores == null || !scores.has(meta.scoreKey)) return@mapNotNull null
        val n = scores.optInt(meta.scoreKey, -1)
        if (n < 0) return@mapNotNull null
        organLabel(meta.key) to n
    }
    if (scored.isNotEmpty()) {
        val avg = scored.map { it.second }.average()
        lines.add(
            "$organScoresHeading：" +
                scored.joinToString("、") { "${it.first}${it.second}" } +
                "（均 ${"%.1f".format(avg)}）"
        )
    }

    val flagged = ORGAN_SCORE_META.mapNotNull { meta ->
        if (meta.femaleOnly && !female) return@mapNotNull null
        val score = scores?.optInt(meta.scoreKey, -1)?.takeIf { it >= 0 }
        val label = patternDisplayLabel(score, patterns?.optString(meta.patternKey))
        if (label.isBlank() || label == "健康" || label == "待觀察") return@mapNotNull null
        "${organLabel(meta.key)}$label"
    }
    if (flagged.isNotEmpty()) {
        lines.add("主要證型：" + flagged.joinToString("、"))
    }

    val advice = json.optString("diet_advice").trim()
    if (advice.isNotBlank()) {
        lines.add("食療整理：$advice")
    }

    val findings = json.optJSONArray("findings")
    if (findings != null) {
        var shown = 0
        for (i in 0 until findings.length()) {
            if (shown >= 5) break
            var text = findings.optString(i).trim()
            if (text.isBlank()) continue
            if (!female && text.contains("子宮")) continue
            // Hide face color-teaching blocks under 食療整理 / findings.
            if (text.startsWith("教學正常值") || text.contains("臉色分數") ||
                text.contains("ΔE*/20") || text.contains("8–10 健康") ||
                text.contains("8-10 健康")
            ) {
                continue
            }
            if (text.length > 80) text = text.take(80) + "…"
            lines.add("・$text")
            shown++
        }
    }
    return lines.joinToString("\n")
}

fun sourceKeyLabel(key: String): String = when (key) {
    "face" -> "臉色"
    "tongue_body" -> "舌色"
    "tongue_coat" -> "舌苔"
    "stool" -> "大便"
    "urine" -> "尿尿"
    "pulse" -> "脈搏"
    else -> key
}
