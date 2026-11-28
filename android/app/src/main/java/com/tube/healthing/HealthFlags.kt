package com.tube.healthing

import android.view.ViewGroup
import android.widget.CheckBox
import android.widget.GridLayout
import org.json.JSONArray
import org.json.JSONObject

data class FlagOption(val value: String, val label: String)

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
    // Offline fallback values (zh). Live labels come from GET /api/flags?lang=.
    val ALLERGIES = listOf(
        "蝦蟹", "魚", "芒果", "花生", "堅果", "雞蛋", "牛奶",
        "優格", "南瓜子", "味噌", "夏威夷豆", "大麥", "奶油", "小麥",
        "山葵", "杏仁果", "松子", "栗子", "核桃", "淡菜", "燕麥", "牡蠣",
        "白芝麻", "皮蛋", "芥末", "花生油", "芹菜", "葡萄酒", "蕎麥",
        "蛋", "蛋白", "蛋黃", "蛤蜊", "豆干", "豆漿", "豆腐", "起司",
        "醋", "醬油", "麻油", "黃豆", "黃豆芽", "黃酒", "黑豆",
    )

    fun optionsFrom(raw: List<String>): List<FlagOption> =
        raw.map { FlagOption(value = it, label = it) }

    fun optionsFromJson(arr: JSONArray?): List<FlagOption> {
        if (arr == null) return emptyList()
        val out = ArrayList<FlagOption>(arr.length())
        for (i in 0 until arr.length()) {
            val item = arr.opt(i)
            when (item) {
                is JSONObject -> {
                    val value = item.optString("value").ifBlank {
                        item.optString("name_zh")
                    }.trim()
                    val label = item.optString("label").ifBlank {
                        item.optString("name")
                    }.ifBlank { value }.trim()
                    if (value.isNotEmpty()) out.add(FlagOption(value, label.ifBlank { value }))
                }
                else -> {
                    val text = arr.optString(i).trim()
                    if (text.isNotEmpty()) out.add(FlagOption(text, text))
                }
            }
        }
        return out
    }

    private val CRUSTACEAN_TOKENS = setOf("蝦蟹", "蝦", "蝦米", "蝦仁", "龍蝦", "螃蟹", "蟹")

    private val FISH_TOKENS = setOf(
        "魚",
        "鯉魚",
        "鯽魚",
        "鱸魚",
        "草魚",
        "鰱魚",
        "青魚",
        "帶魚",
        "黃魚",
        "鯖魚",
        "鮪魚",
        "鮭魚",
        "鱈魚",
        "鯛魚",
        "秋刀魚",
        "沙丁魚",
        "鰻魚",
        "鱔魚",
        "虱目魚",
        "石斑魚",
        "比目魚",
        "鯊魚",
        "烏魚",
        "鰹魚",
        "吳郭魚",
        "鮑魚",
        "魷魚",
        "章魚", // no 魚 glyph; still treated as fish allergy token
    )

    fun canonicalizeAllergyLabel(label: String?): String? {
        val text = label?.trim().orEmpty()
        if (text.isEmpty()) return null
        if (text in CRUSTACEAN_TOKENS) return "蝦蟹"
        if (text in FISH_TOKENS || "魚" in text) return "魚"
        return text
    }

    fun consolidateAllergyOptions(options: List<String>): List<String> {
        val ordered = ArrayList<String>()
        val seen = HashSet<String>()
        for (label in options) {
            val canon = canonicalizeAllergyLabel(label) ?: continue
            if (seen.add(canon)) ordered.add(canon)
        }
        return ordered
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

    /** Inflate checkboxes; if [parent] is a [GridLayout], use equal-width columns. */
    fun inflate(parent: ViewGroup, options: List<String>, columns: Int = 1) {
        inflateOptions(parent, optionsFrom(options), columns)
    }

    fun inflateOptions(parent: ViewGroup, options: List<FlagOption>, columns: Int = 1) {
        parent.removeAllViews()
        val grid = parent as? GridLayout
        if (grid != null && columns > 1) {
            grid.columnCount = columns
        }
        options.forEach { opt ->
            val box = CheckBox(parent.context).apply {
                text = opt.label
                tag = opt.value
            }
            if (grid != null) {
                val lp = GridLayout.LayoutParams().apply {
                    width = 0
                    height = ViewGroup.LayoutParams.WRAP_CONTENT
                    columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f)
                }
                parent.addView(box, lp)
            } else {
                parent.addView(box)
            }
        }
    }

    fun selectedJson(parent: ViewGroup): String {
        val arr = JSONArray()
        for (i in 0 until parent.childCount) {
            val box = parent.getChildAt(i) as? CheckBox ?: continue
            if (box.isChecked) {
                val value = (box.tag as? String)?.trim().orEmpty().ifBlank { box.text.toString() }
                arr.put(value)
            }
        }
        return arr.toString()
    }

    fun apply(parent: ViewGroup, selected: JSONArray?) {
        val picked = mutableSetOf<String>()
        if (selected != null) {
            for (i in 0 until selected.length()) {
                val raw = selected.optString(i)
                canonicalizeAllergyLabel(raw)?.let { picked.add(it) }
                raw.trim().takeIf { it.isNotEmpty() }?.let { picked.add(it) }
            }
        }
        for (i in 0 until parent.childCount) {
            val box = parent.getChildAt(i) as? CheckBox ?: continue
            val value = (box.tag as? String)?.trim().orEmpty().ifBlank { box.text.toString() }
            box.isChecked = value in picked || box.text.toString() in picked
        }
    }
}
