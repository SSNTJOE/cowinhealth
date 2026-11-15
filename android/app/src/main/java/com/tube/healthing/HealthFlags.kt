package com.tube.healthing

import android.widget.CheckBox
import android.widget.LinearLayout
import org.json.JSONArray
import org.json.JSONObject

object HealthFlags {
    val CONDITIONS = listOf(
        "糖尿病",
        "中風",
        "痛風",
        "腎臟病",
        "肝病",
        "高血壓",
        "服用抗凝血劑",
    )
    val ALLERGIES = listOf("蝦蟹", "魚", "芒果", "花生", "堅果", "雞蛋", "牛奶")

    private val CRUSTACEAN_TOKENS = setOf("蝦蟹", "蝦", "蝦米", "蝦仁", "龍蝦", "螃蟹", "蟹")

    fun canonicalizeAllergyLabel(label: String?): String? {
        val text = label?.trim().orEmpty()
        if (text.isEmpty()) return null
        if (text in CRUSTACEAN_TOKENS) return "蝦蟹"
        if ("魚" in text) return "魚"
        return text
    }

    fun jsonLabels(arr: JSONArray?): List<String> {
        if (arr == null) return emptyList()
        val out = ArrayList<String>(arr.length())
        for (i in 0 until arr.length()) {
            val label = arr.optString(i).trim()
            if (label.isNotEmpty()) out.add(label)
        }
        return out
    }

    fun jsonLabelsFrom(obj: JSONObject?, vararg keys: String): List<String> {
        if (obj == null) return emptyList()
        for (key in keys) {
            if (!obj.has(key) || obj.isNull(key)) continue
            val labels = jsonLabels(asArray(obj.opt(key)))
            if (labels.isNotEmpty()) return labels
        }
        return emptyList()
    }

    private fun asArray(raw: Any?): JSONArray? {
        return when (raw) {
            is JSONArray -> raw
            is Collection<*> -> JSONArray(raw)
            is String -> {
                val text = raw.trim()
                if (text.startsWith("[")) JSONArray(text) else null
            }
            else -> null
        }
    }

    fun inflate(parent: LinearLayout, options: List<String>) {
        parent.removeAllViews()
        options.forEach { label ->
            parent.addView(
                CheckBox(parent.context).apply {
                    text = label
                    tag = label
                }
            )
        }
    }

    fun selectedJson(parent: LinearLayout): String {
        val arr = JSONArray()
        for (i in 0 until parent.childCount) {
            val box = parent.getChildAt(i) as? CheckBox ?: continue
            if (box.isChecked) arr.put(box.text.toString())
        }
        return arr.toString()
    }

    fun apply(parent: LinearLayout, selected: JSONArray?) {
        val picked = mutableSetOf<String>()
        if (selected != null) {
            for (i in 0 until selected.length()) {
                canonicalizeAllergyLabel(selected.optString(i))?.let { picked.add(it) }
            }
        }
        for (i in 0 until parent.childCount) {
            val box = parent.getChildAt(i) as? CheckBox ?: continue
            box.isChecked = picked.contains(box.text.toString())
        }
    }
}
