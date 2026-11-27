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

/** Default shoot prompts when server omits missing_source_prompts (offline / old records). */
fun defaultOrganShootPrompt(organKey: String): String = when (organKey) {
    "heart", "lung", "uterus" -> "請拍攝臉／舌以便判讀"
    "liver", "spleen", "stomach", "gallbladder", "large_intestine", "small_intestine" ->
        "請拍攝臉／舌／大便以便判讀"
    "kidney" -> "請拍攝臉／舌／尿尿以便判讀"
    "bladder" -> "請拍攝尿尿以便判讀"
    else -> "請拍攝以便判讀"
}

fun organShootPrompt(
    organKey: String,
    scoreKey: String,
    organHealth: JSONObject?,
): String {
    val prompts = organHealth?.optJSONObject("missing_source_prompts")
    if (prompts != null) {
        val byScore = prompts.optString(scoreKey).trim()
        if (byScore.isNotEmpty()) return byScore
        val byKey = prompts.optString(organKey).trim()
        if (byKey.isNotEmpty()) return byKey
    }
    val organs = organHealth?.optJSONObject("organs")
    val info = organs?.optJSONObject(organKey)
    val nested = info?.optString("shoot_prompt").orEmpty().trim()
    if (nested.isNotEmpty()) return nested
    return defaultOrganShootPrompt(organKey)
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
    organHealth: JSONObject? = null,
) {
    grid.removeAllViews()
    val ctx = grid.context
    ORGAN_SCORE_META.forEach { meta ->
        if (meta.femaleOnly && !female) return@forEach
        val score = when {
            scores == null -> null
            scores.has(meta.scoreKey) -> scores.optInt(meta.scoreKey, -1).takeIf { it in 1..10 }
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
        if (score == null) {
            cell.addView(TextView(ctx).apply {
                text = organShootPrompt(meta.key, meta.scoreKey, organHealth)
                textSize = 12f
                setTypeface(typeface, android.graphics.Typeface.BOLD)
                setTextColor(Color.parseColor("#616161"))
            })
        } else {
            cell.addView(TextView(ctx).apply {
                text = score.toString()
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
        if (n !in 1..10) return@mapNotNull null
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

    // Face / tongue: short color conclusions only — no cell / Lab / zone prose.
    for (line in faceFinalConclusions(json)) {
        lines.add(line)
    }
    for (line in tongueFinalConclusions(json)) {
        lines.add(line)
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
            // Between 教學示範非診斷 and 臟腑分數趨勢: hide face/tongue color-judgment detail.
            if (isFaceOrTongueColorDetail(text)) continue
            // Stool / urine already emitted as brief conclusions above.
            if (text.startsWith("大便") || text.startsWith("尿尿")) continue
            if (text.length > 80) text = text.take(80) + "…"
            lines.add("・$text")
            shown++
        }
    }
    return lines.joinToString("\n")
}

/** Drop Lab / YCrCb measurement asides; keep TCM conclusion words. */
fun stripColorMeasurementProse(text: String): String {
    var s = text.trim()
    s = s.replace(Regex("""（[^）]*(?:Cr|Cb|Δ[CELab]|ΔE|L\*|a\*|b\*|YCrCb|教學|色澤|健康分)[^）]*）"""), "")
    s = s.replace(Regex("""\([^)]*(?:Cr|Cb|Δ[CELab]|ΔE|L\*|a\*|b\*|YCrCb)[^)]*\)"""), "")
    s = s.replace(Regex("""#[0-9A-Fa-f]{6}"""), "")
    s = s.replace(Regex("""\s*[Δ]?Cr\s*[-+]?\d+(\.\d+)?"""), "")
    s = s.replace(Regex("""\s*[Δ]?Cb\s*[-+]?\d+(\.\d+)?"""), "")
    s = s.replace(Regex("""\s{2,}"""), " ").trim()
    return s.trim('，', ',', '／', '/', ' ', '→', '-')
}

/**
 * Face / tongue color-judgment *statements* (cells, Lab, zones, teaching blobs).
 * Short conclusions are emitted separately via faceFinalConclusions / tongueFinalConclusions.
 */
fun isFaceOrTongueColorDetail(text: String): Boolean {
    if (text.isBlank()) return false
    if (text.startsWith("教學正常值") || text.contains("臉色分數") ||
        text.contains("ΔE*/20") || text.contains("8–10 健康") || text.contains("8-10 健康")
    ) {
        return true
    }
    if (Regex("""第\d+格""").containsMatchIn(text)) return true
    if (text.contains("ΔCr") || text.contains("ΔCb") || text.contains("L*") ||
        text.contains("a*") || text.contains("b*") || text.contains("YCrCb")
    ) {
        return true
    }
    if (Regex("""\bCr\s*[-+]?\d""").containsMatchIn(text) ||
        Regex("""\bCb\s*[-+]?\d""").containsMatchIn(text)
    ) {
        return true
    }
    if (text.startsWith("面色") || text.startsWith("臉色") || text.startsWith("唇") ||
        text.startsWith("額頭") || text.contains("滿面") || text.contains("兩頰") ||
        text.contains("下頜") || text.contains("白睛") || text.contains("眼眥") ||
        text.contains("眼瞼") || text.contains("瞼內")
    ) {
        return true
    }
    if (text.contains("未見明顯偏色") || text.contains("未見全臉色偏") ||
        text.contains("未見明顯色差")
    ) {
        return true
    }
    if (isTongueRegionalFinding(text)) return true
    if (text.startsWith("舌質") || text.startsWith("舌苔") || text.startsWith("舌苔（") ||
        text.startsWith("黃苔") || text.startsWith("白苔") || text.startsWith("剝苔")
    ) {
        return true
    }
    if (text.contains("舌質") || text.contains("舌苔") ||
        (text.contains("舌") && text.contains("→"))
    ) {
        return true
    }
    return false
}

/** Regional tongue zone lines like 中（脾胃／舌中）… — hide on App UX. */
fun isTongueRegionalFinding(text: String): Boolean {
    if (text.isBlank()) return false
    val regionalMarkers = listOf(
        "（脾胃／舌中）", "（心肺／舌尖）", "（腎／舌根）",
        "（肝膽／舌邊）", "／舌中）", "／舌尖）", "／舌根）", "／舌邊）",
        "舌尖−舌中", "舌尖-舌中", "心肺區偏紅", "上區舌質",
        "上（腎", "中（脾胃", "下（心肺", "左（肝膽", "右（肝膽",
    )
    if (regionalMarkers.any { text.contains(it) }) return true
    // "上／中／下／左／右（…）舌質…" zone headers from analysis.py
    if (Regex("""^[上下中左右]（[^）]+）""").containsMatchIn(text)) return true
    return false
}

/** Short face color conclusion only (bias / lip), no cell or Lab teaching prose. */
fun faceFinalConclusions(json: JSONObject): List<String> {
    val out = mutableListOf<String>()
    val faceGrid = json.optJSONObject("face_grid")
    val complexion = faceGrid?.optJSONObject("complexion")
        ?: json.optJSONObject("complexion")
    val bias = complexion?.optString("bias")?.trim().orEmpty()
    if (bias.isNotBlank() && bias != "基本色" && bias != "色差基準") {
        out.add("臉色：${stripColorMeasurementProse(bias)}")
    } else {
        val dm = json.optJSONObject("organ_health")?.optJSONObject("day_modalities")
            ?: json.optJSONObject("day_modalities")
        val label = dm?.optJSONObject("face")?.optString("color_label")?.trim().orEmpty()
        when {
            label.isBlank() -> Unit
            label == "臉色已測" || label == "已測" -> out.add("臉色：已測")
            !isFaceOrTongueColorDetail(label) && label.length <= 24 -> {
                out.add(if (label.startsWith("臉")) label else "臉色：$label")
            }
            else -> {
                // Pull a short TCM bias token from a long teaching label when possible.
                val token = listOf("實熱", "實寒", "虛熱", "虛寒", "濕氣", "血瘀")
                    .firstOrNull { label.contains(it) }
                if (token != null) out.add("臉色：$token")
            }
        }
    }
    val lip = json.optJSONObject("region_colors")?.optString("lip_color")?.trim().orEmpty()
    if (lip.isNotBlank()) {
        val short = stripColorMeasurementProse(lip.removePrefix("唇").trim())
        if (short.isNotBlank()) out.add("唇：$short")
    }
    return out
}

/** Final tongue conclusions only (舌質 + 舌苔), from region_colors / day_modalities. */
fun tongueFinalConclusions(json: JSONObject): List<String> {
    val out = mutableListOf<String>()
    val colors = json.optJSONObject("region_colors")
    val body = stripColorMeasurementProse(colors?.optString("tongue_body_color").orEmpty())
    val coat = stripColorMeasurementProse(colors?.optString("tongue_coat_color").orEmpty())
    if (body.isNotBlank()) out.add("舌質：$body")
    if (coat.isNotBlank()) out.add("舌苔：$coat")
    if (out.isNotEmpty()) return out

    // Fallback: day_modalities.tongue.color_label like "舌質偏紅 → …；黃苔 → …"
    val dm = json.optJSONObject("organ_health")?.optJSONObject("day_modalities")
        ?: json.optJSONObject("day_modalities")
    val label = dm?.optJSONObject("tongue")?.optString("color_label")?.trim().orEmpty()
    if (label.isBlank() || isTongueRegionalFinding(label)) return out
    if (label.contains("舌質") || label.contains("舌苔") || label.contains("→")) {
        // Split composite "舌質…；苔…" into two lines when possible.
        val parts = label.split("；", ";", "／").map { it.trim() }.filter { it.isNotBlank() }
        if (parts.size >= 2) {
            val bodyPart = stripColorMeasurementProse(parts.firstOrNull { it.contains("舌質") } ?: parts[0])
            val coatPart = stripColorMeasurementProse(parts.firstOrNull { it.contains("苔") } ?: parts[1])
            out.add(if (bodyPart.startsWith("舌質")) bodyPart else "舌質：$bodyPart")
            out.add(if (coatPart.startsWith("舌苔") || coatPart.startsWith("苔")) {
                if (coatPart.startsWith("舌苔")) coatPart else "舌苔：$coatPart"
            } else "舌苔：$coatPart")
        } else {
            val short = stripColorMeasurementProse(label)
            out.add(if (short.startsWith("舌")) short else "舌：$short")
        }
    }
    return out
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
