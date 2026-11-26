package com.tube.healthing

import org.json.JSONArray
import org.json.JSONObject

/**
 * Teaching-demo stool / urine → short normal vs concern text.
 * Mirrors server [app/stool_urine.py] class labels (abnormal flag).
 */
object StoolUrineJudge {
    data class ClassHit(
        val id: String,
        val label: String,
        val organs: String,
        val hint: String,
        val healthScore: Int,
        val abnormal: Boolean,
        val organKeys: List<String>,
    )

    data class OrganLine(
        val name: String,
        val display: String,
        val score: Int,
        val note: String,
    )

    fun extractClass(note: JSONObject?): ClassHit? {
        if (note == null) return null
        val cls = note.optJSONObject("class") ?: return null
        val keys = mutableListOf<String>()
        val arr = cls.optJSONArray("organ_keys")
        if (arr != null) {
            for (i in 0 until arr.length()) {
                val k = arr.optString(i).trim()
                if (k.isNotBlank()) keys.add(k)
            }
        }
        val label = cls.optString("label").trim()
        if (label.isBlank() && keys.isEmpty()) return null
        return ClassHit(
            id = cls.optString("id").trim(),
            label = label.ifBlank { "未分類" },
            organs = cls.optString("organs").trim(),
            hint = cls.optString("hint").trim(),
            healthScore = cls.optInt("health_score", 8).coerceIn(1, 10),
            abnormal = cls.optBoolean("abnormal", false),
            organKeys = keys,
        )
    }

    fun shortLine(line: OrganLine): String {
        return "${line.name}：${line.display}（${line.note}，約${line.score}分）"
    }

    private fun displayFor(score: Int, pattern: String?, abnormal: Boolean): String {
        val fromPattern = patternDisplayLabel(score, pattern)
        if (fromPattern.isNotBlank()) return fromPattern
        return when {
            score >= 8 -> "健康"
            abnormal && score <= 4 -> "需留意"
            else -> "待觀察"
        }
    }

    private fun noteSnippet(hit: ClassHit?): String {
        val label = hit?.label?.trim().orEmpty()
        if (label.isNotBlank()) return label.take(18)
        return "教學色調"
    }

    private fun scoresForKind(json: JSONObject, kind: String, hit: ClassHit?): Map<String, Int> {
        val out = LinkedHashMap<String, Int>()
        val note = noteForKind(json, kind)
        val nested = note?.optJSONObject("organ_scores")
        if (nested != null) {
            ORGAN_SCORE_META.forEach { meta ->
                if (nested.has(meta.scoreKey)) {
                    val n = nested.optInt(meta.scoreKey, -1)
                    if (n >= 0) out[meta.key] = n.coerceIn(1, 10)
                }
            }
        }
        if (out.isEmpty()) {
            val top = json.optJSONObject("scores")
            val keys = hit?.organKeys.orEmpty().toSet()
            ORGAN_SCORE_META.forEach { meta ->
                if (keys.isNotEmpty() && meta.key !in keys) return@forEach
                if (top != null && top.has(meta.scoreKey)) {
                    val n = top.optInt(meta.scoreKey, -1)
                    if (n >= 0) out[meta.key] = n.coerceIn(1, 10)
                }
            }
        }
        if (out.isEmpty() && hit != null) {
            hit.organKeys.forEach { key -> out[key] = hit.healthScore.coerceIn(1, 10) }
        }
        return out
    }

    fun organLines(json: JSONObject, kind: String): List<OrganLine> {
        val note = noteForKind(json, kind)
        val hit = extractClass(note)
        val scores = scoresForKind(json, kind, hit)
        if (scores.isEmpty()) return emptyList()
        val patterns = json.optJSONObject("patterns")
        val snippet = noteSnippet(hit)
        return ORGAN_SCORE_META.mapNotNull { meta ->
            val score = scores[meta.key] ?: return@mapNotNull null
            val rawPattern = patterns?.optString(meta.patternKey).orEmpty()
            OrganLine(
                name = meta.name,
                display = displayFor(score, rawPattern.ifBlank { null }, hit?.abnormal == true),
                score = score,
                note = snippet,
            )
        }
    }

    /** Prefer top-level stool/urine; fall back to organ_health.stool_urine / day_modalities. */
    fun noteForKind(json: JSONObject, kind: String): JSONObject? {
        // Top-level from /api/record is always the just-shot modality when present.
        json.optJSONObject(kind)?.let { note ->
            if (note.optJSONObject("class") != null || note.has("lab")) return note
        }
        val health = json.optJSONObject("organ_health")
        health?.optJSONObject("stool_urine")?.optJSONObject(kind)?.let { note ->
            if (note.optJSONObject("class") != null || note.has("lab")) return note
        }
        // day_modalities.<kind>.note carries the full teaching note across same-day merges.
        health?.optJSONObject("day_modalities")?.optJSONObject(kind)?.optJSONObject("note")?.let {
            return it
        }
        return json.optJSONObject(kind)
            ?: health?.optJSONObject("stool_urine")?.optJSONObject(kind)
    }

    /** Newest findings line for this modality (server writes 「大便：…」/「尿尿：…」). */
    fun findingLine(json: JSONObject, kind: String): String? {
        val isUrine = kind == CameraFacing.URINE || kind == "urine"
        // Prefer exact modality tags; avoid bare 「尿」 which is too broad.
        val prefixes = if (isUrine) {
            listOf("尿尿")
        } else {
            listOf("大便", "大便色")
        }
        fun lastMatch(arr: JSONArray?): String? {
            if (arr == null) return null
            var hit: String? = null
            for (i in 0 until arr.length()) {
                val raw = arr.optString(i).trim()
                if (raw.isBlank()) continue
                if (prefixes.any { raw.startsWith(it) }) {
                    hit = raw.split("（").first().trim()
                }
            }
            return hit
        }
        lastMatch(json.optJSONArray("findings"))?.let { return it }
        val dm = json.optJSONObject("organ_health")
            ?.optJSONObject("day_modalities")
            ?.optJSONObject(if (isUrine) "urine" else "stool")
        lastMatch(dm?.optJSONArray("findings"))?.let { return it }
        val label = dm?.optString("color_label")?.trim().orEmpty()
        if (label.isNotBlank()) {
            val tag = if (isUrine) "尿尿" else "大便"
            return if (label.startsWith(tag)) label else "$tag：$label"
        }
        return null
    }

    /** One short line: normal vs notes of concern (existing class rules). */
    fun briefStatus(json: JSONObject, kind: String): String {
        val isUrine = kind == CameraFacing.URINE || kind == "urine"
        val tag = if (isUrine) "尿尿" else "大便"
        val note = noteForKind(json, kind)
        val hit = extractClass(note)
        // Prefer class label; avoid using multi-modality composite color_label as the stool/urine name.
        val rawColor = json.optString("color_label").trim()
        val colorFallback = when {
            rawColor.startsWith(tag) -> rawColor.removePrefix("$tag：").removePrefix("$tag:").trim()
            rawColor.contains("／") || rawColor.startsWith("臉") || rawColor.startsWith("舌") -> ""
            rawColor.isNotBlank() && rawColor != "尚未拍照" -> rawColor
            else -> ""
        }
        val label = hit?.label?.trim()
            ?.ifBlank { null }
            ?: colorFallback.ifBlank { null }
            ?: findingLine(json, kind)?.substringAfter("：")?.substringAfter(":")?.trim()
            ?: "未分類"
        if (hit == null && label == "未分類") {
            return findingLine(json, kind) ?: "$tag：尚無色調判斷"
        }
        val concernExtra = buildList {
            if (isUrine) {
                val foam = note?.optJSONObject("foam")
                when (foam?.optString("granularity")) {
                    "fine_dense" -> add("細密泡沫")
                    "coarse_sparse" -> add("粗疏泡沫")
                    "mixed" -> add("混合泡沫")
                }
                if (foam?.optBoolean("persistent_foam_teaching_alert", false) == true) {
                    add("泡沫持續警覺")
                }
            } else {
                val steat = note?.optJSONObject("steatorrhea")
                if (steat?.optBoolean("triggered", false) == true || hit?.id == "pale_oily") {
                    add("油光／淡脂線索")
                }
            }
        }
        val classObj = note?.optJSONObject("class")
        val offPalette = hit?.id == "outside_palette" ||
            hit?.id == "possible_stain" ||
            classObj?.optBoolean("far_from_palette", false) == true ||
            label.contains("偏離教學色盤") ||
            label.contains("無法對照") ||
            label.contains("可能染色")
        if (offPalette) {
            val hint = hit?.hint?.take(48).orEmpty()
                .ifBlank { classObj?.optString("hint").orEmpty().take(48) }
            return if (hint.isNotBlank()) "$tag：無法對照 — $label（$hint）"
            else "$tag：無法對照 — $label"
        }
        return if (hit?.abnormal == true) {
            val hint = hit.hint.take(24).ifBlank { hit.organs.take(24) }
            val extra = if (concernExtra.isNotEmpty()) "；" + concernExtra.joinToString("、") else ""
            if (hint.isNotBlank()) "$tag：需留意 — $label（$hint$extra）"
            else "$tag：需留意 — $label$extra"
        } else {
            "$tag：正常 — $label"
        }
    }

    /** Brief conclusion block shown after 拍大便／拍尿尿. */
    fun summaryFromResult(json: JSONObject, kind: String): String {
        val isUrine = kind == CameraFacing.URINE || kind == "urine"
        val title = if (isUrine) {
            "尿尿色診（教學參考，非診斷）"
        } else {
            "大便色診（教學參考，非診斷）"
        }
        val status = briefStatus(json, kind)
        // Keep urine narrative short: title + one status line only.
        return if (isUrine) {
            listOf(title, status).joinToString("\n")
        } else {
            listOf(title, status).joinToString("\n")
        }
    }

    /** Combined stool + urine short panel (both stay visible). */
    fun panelText(json: JSONObject): String {
        val lines = mutableListOf<String>()
        val hasStool = noteForKind(json, "stool") != null || findingLine(json, "stool") != null
        val hasUrine = noteForKind(json, "urine") != null || findingLine(json, "urine") != null
        if (hasStool) lines.add(briefStatus(json, "stool"))
        if (hasUrine) lines.add(briefStatus(json, "urine"))
        if (lines.isEmpty()) {
            findingLine(json, "stool")?.let { lines.add(it) }
            findingLine(json, "urine")?.let { lines.add(it) }
        }
        if (lines.isEmpty()) {
            val label = json.optString("color_label").trim()
            if (label.startsWith("尿尿") || label.startsWith("大便")) lines.add(label)
        }
        return lines.joinToString("\n")
    }

    /** One-line toast companion. */
    fun toastLine(json: JSONObject, kind: String): String {
        return briefStatus(json, kind)
    }
}
