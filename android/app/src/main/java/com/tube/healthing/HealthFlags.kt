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

    private val CONDITION_I18N = mapOf(
        "糖尿病" to mapOf("en" to "Diabetes", "ja" to "糖尿病", "ko" to "당뇨병"),
        "中風" to mapOf("en" to "Stroke", "ja" to "脳卒中", "ko" to "뇌졸중"),
        "痛風" to mapOf("en" to "Gout", "ja" to "痛風", "ko" to "통풍"),
        "腎臟病" to mapOf("en" to "Kidney disease", "ja" to "腎臓病", "ko" to "신장병"),
        "肝病" to mapOf("en" to "Liver disease", "ja" to "肝疾患", "ko" to "간질환"),
        "高血壓" to mapOf("en" to "Hypertension", "ja" to "高血圧", "ko" to "고혈압"),
        "服用抗凝血劑" to mapOf(
            "en" to "Taking anticoagulants",
            "ja" to "抗凝固薬を服用中",
            "ko" to "항응고제 복용",
        ),
    )

    // Offline fallback values (zh). Live labels come from GET /api/flags?lang=.
    val ALLERGIES = listOf(
        "蝦蟹", "魚", "芒果", "花生", "堅果", "雞蛋", "牛奶",
        "優格", "南瓜", "味噌", "夏威夷豆", "大麥", "奶油", "小麥",
        "山葵", "杏仁果", "松子", "栗子", "核桃", "淡菜", "燕麥", "牡蠣",
        "白芝麻", "皮蛋", "芥末", "花生油", "芹菜", "葡萄酒", "蕎麥",
        "蛋", "蛋白", "蛋黃", "蛤蜊", "豆干", "豆漿", "豆腐", "起司",
        "醋", "醬油", "麻油", "黃豆", "黃豆芽", "黃酒", "黑豆",
    )

    private val ALLERGEN_I18N = mapOf(
        "蝦蟹" to mapOf("en" to "Shellfish (shrimp/crab)", "ja" to "エビ・カニ", "ko" to "새우·게"),
        "魚" to mapOf("en" to "Fish", "ja" to "魚", "ko" to "생선"),
        "芒果" to mapOf("en" to "Mango", "ja" to "マンゴー", "ko" to "망고"),
        "花生" to mapOf("en" to "Peanut", "ja" to "落花生", "ko" to "땅콩"),
        "堅果" to mapOf("en" to "Tree nuts", "ja" to "ナッツ類", "ko" to "견과류"),
        "雞蛋" to mapOf("en" to "Egg", "ja" to "鶏卵", "ko" to "달걀"),
        "牛奶" to mapOf("en" to "Milk", "ja" to "牛乳", "ko" to "우유"),
        "優格" to mapOf("en" to "Yogurt", "ja" to "ヨーグルト", "ko" to "요거트"),
        "南瓜" to mapOf("en" to "Pumpkin", "ja" to "かぼちゃ", "ko" to "호박"),
        "南瓜子" to mapOf("en" to "Pumpkin seeds", "ja" to "かぼちゃの種", "ko" to "호박씨"),
        "味噌" to mapOf("en" to "Miso", "ja" to "味噌", "ko" to "미소"),
        "夏威夷豆" to mapOf("en" to "Macadamia", "ja" to "マカダミア", "ko" to "마카다미아"),
        "大麥" to mapOf("en" to "Barley", "ja" to "オオムギ", "ko" to "보리"),
        "奶油" to mapOf("en" to "Butter", "ja" to "バター", "ko" to "버터"),
        "小麥" to mapOf("en" to "Wheat", "ja" to "コムギ", "ko" to "밀"),
        "山葵" to mapOf("en" to "Wasabi", "ja" to "ワサビ", "ko" to "와사비"),
        "杏仁果" to mapOf("en" to "Almond", "ja" to "アーモンド", "ko" to "아몬드"),
        "松子" to mapOf("en" to "Pine nut", "ja" to "松の実", "ko" to "잣"),
        "栗子" to mapOf("en" to "Chestnut", "ja" to "栗", "ko" to "밤"),
        "核桃" to mapOf("en" to "Walnut", "ja" to "クルミ", "ko" to "호두"),
        "淡菜" to mapOf("en" to "Mussel", "ja" to "ムール貝", "ko" to "홍합"),
        "燕麥" to mapOf("en" to "Oat", "ja" to "オート麦", "ko" to "귀리"),
        "牡蠣" to mapOf("en" to "Oyster", "ja" to "カキ", "ko" to "굴"),
        "白芝麻" to mapOf("en" to "White sesame", "ja" to "白ごま", "ko" to "흰깨"),
        "皮蛋" to mapOf("en" to "Century egg", "ja" to "ピータン", "ko" to "피단"),
        "芥末" to mapOf("en" to "Mustard", "ja" to "カラシ", "ko" to "겨자"),
        "花生油" to mapOf("en" to "Peanut oil", "ja" to "ピーナッツ油", "ko" to "땅콩기름"),
        "芹菜" to mapOf("en" to "Celery", "ja" to "セロリ", "ko" to "셀러리"),
        "葡萄酒" to mapOf("en" to "Wine", "ja" to "ワイン", "ko" to "와인"),
        "蕎麥" to mapOf("en" to "Buckwheat", "ja" to "ソバ", "ko" to "메밀"),
        "蛋" to mapOf("en" to "Egg", "ja" to "卵", "ko" to "달걀"),
        "蛋白" to mapOf("en" to "Egg white", "ja" to "卵白", "ko" to "달걀흰자"),
        "蛋黃" to mapOf("en" to "Egg yolk", "ja" to "卵黄", "ko" to "달걀노른자"),
        "蛤蜊" to mapOf("en" to "Clam", "ja" to "アサリ", "ko" to "바지락"),
        "豆干" to mapOf("en" to "Dried tofu", "ja" to "豆腐干", "ko" to "포두부"),
        "豆漿" to mapOf("en" to "Soy milk", "ja" to "豆乳", "ko" to "두유"),
        "豆腐" to mapOf("en" to "Tofu", "ja" to "豆腐", "ko" to "두부"),
        "起司" to mapOf("en" to "Cheese", "ja" to "チーズ", "ko" to "치즈"),
        "醋" to mapOf("en" to "Vinegar", "ja" to "酢", "ko" to "식초"),
        "醬油" to mapOf("en" to "Soy sauce", "ja" to "醤油", "ko" to "간장"),
        "麻油" to mapOf("en" to "Sesame oil", "ja" to "ごま油", "ko" to "참기름"),
        "黃豆" to mapOf("en" to "Soybean", "ja" to "大豆", "ko" to "대두"),
        "黃豆芽" to mapOf("en" to "Soybean sprouts", "ja" to "大豆もやし", "ko" to "콩나물"),
        "黃酒" to mapOf("en" to "Yellow rice wine", "ja" to "黄酒", "ko" to "황주"),
        "黑豆" to mapOf("en" to "Black soybean", "ja" to "黒豆", "ko" to "검은콩"),
    )

    fun localizeCondition(zh: String, lang: String): String {
        if (lang == "zh" || zh.isBlank()) return zh
        return CONDITION_I18N[zh]?.get(lang) ?: zh
    }

    fun localizeAllergy(zh: String, lang: String): String {
        if (lang == "zh" || zh.isBlank()) return zh
        return ALLERGEN_I18N[zh]?.get(lang) ?: zh
    }

    fun localizedAllergyOptions(lang: String): List<FlagOption> =
        ALLERGIES.map { FlagOption(value = it, label = localizeAllergy(it, lang)) }

    fun localizedConditionOptions(lang: String): List<FlagOption> =
        CONDITIONS.map { FlagOption(value = it, label = localizeCondition(it, lang)) }

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

    /** Prefer API label; if still zh on a non-zh UI, use builtin. */
    fun displayLabel(opt: FlagOption, lang: String, kind: String = "allergen"): String {
        val raw = opt.label.ifBlank { opt.value }
        if (lang == "zh" || raw != opt.value) return raw
        return if (kind == "condition") localizeCondition(opt.value, lang)
        else localizeAllergy(opt.value, lang)
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
