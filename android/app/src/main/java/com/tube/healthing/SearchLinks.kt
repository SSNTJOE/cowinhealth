package com.tube.healthing

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.TextPaint
import android.text.method.LinkMovementMethod
import android.text.style.ClickableSpan
import android.view.View
import android.widget.TextView
import android.widget.Toast

/**
 * Structured Google Search queries (not Gemini / Copilot).
 *
 * Intent shapes (server [advice.py] builds the same):
 * - 食譜文章: 食譜 + 特殊疾病 + 今日症狀（無症狀則五臟六腑判斷）
 * - 食譜影片: 食譜 + 影片 + … − allergens
 * - 穴道照片: 穴道 + 照片 + …
 * - 穴道影片: 穴道 + 影片 + …
 */
object SearchLinks {
    /** Fluff only — never strip structured intent tokens. */
    private val NOISE = setOf(
        "教學參考食療", "教學參考", "非診斷", "作法", "做法",
        "穴位圖", "按摩手法", "文章", "作法教學",
        "YouTube", "示意圖", "按摩教學", "OR",
        "中醫食譜", "中醫調理", "穴道按摩",
    )

    /** Keep these even when shortening — they define the four search intents. */
    private val INTENT_KEEP = setOf("食譜", "影片", "穴道", "照片", "圖片")

    fun extractQuery(urlOrQuery: String): String {
        val raw = urlOrQuery.trim()
        if (raw.isBlank()) return ""
        return try {
            val uri = Uri.parse(raw)
            uri.getQueryParameter("q")?.trim().orEmpty().ifBlank { raw }
        } catch (_: Exception) {
            raw
        }
    }

    fun shortenQuery(urlOrQuery: String, maxTokens: Int = 12): String {
        val q = extractQuery(urlOrQuery)
        if (q.isBlank()) return ""
        val tokens = q
            .replace("(", " ")
            .replace(")", " ")
            .split(Regex("\\s+"))
            .map { it.trim() }
            .filter { tok ->
                tok.isNotBlank() &&
                    tok !in NOISE &&
                    !tok.equals("OR", ignoreCase = true)
            }
        if (tokens.isEmpty()) {
            return q.split(Regex("\\s+")).filter { it.isNotBlank() }.take(maxTokens).joinToString(" ")
        }
        val intent = tokens.filter { it in INTENT_KEEP }
        val rest = tokens.filter { it !in INTENT_KEEP }
        val merged = (intent + rest).distinct()
        return merged.take(maxTokens).joinToString(" ")
    }

    fun ensureIntentQuery(urlOrQuery: String, vararg required: String): String {
        val short = shortenQuery(urlOrQuery)
        if (short.isBlank()) return ""
        if (required.isEmpty()) return short
        val have = short.split(Regex("\\s+")).toSet()
        val missing = required.filter { it.isNotBlank() && it !in have }
        return if (missing.isEmpty()) short else (missing + short.split(Regex("\\s+"))).distinct().joinToString(" ")
    }

    /** Open plain Google Search with the query (no Gemini / Copilot). */
    fun openSmartSearch(context: Context, urlOrQuery: String) {
        val short = shortenQuery(urlOrQuery)
        if (short.isBlank()) {
            Toast.makeText(context, "沒有可用的搜尋關鍵字", Toast.LENGTH_SHORT).show()
            return
        }
        val encoded = Uri.encode(short)
        val tokens = short.split(Regex("\\s+")).toSet()
        val url = when {
            "影片" in tokens -> "https://www.google.com/search?tbm=vid&q=$encoded"
            "照片" in tokens || "圖片" in tokens -> "https://www.google.com/search?tbm=isch&q=$encoded"
            else -> "https://www.google.com/search?q=$encoded"
        }
        try {
            context.startActivity(
                Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        } catch (_: ActivityNotFoundException) {
            Toast.makeText(context, "無法開啟 Google 搜尋", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(context, "無法開啟搜尋：${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    /**
     * Show clickable **labels only** (no raw URL strings). Each click opens Google Search.
     */
    fun bindLabeledLinks(
        tv: TextView,
        items: List<Pair<String, String>>,
        context: Context,
    ) {
        val kept = items.filter { it.first.isNotBlank() && it.second.isNotBlank() }
        if (kept.isEmpty()) {
            tv.text = ""
            return
        }
        val sb = SpannableStringBuilder()
        kept.forEachIndexed { index, (label, urlOrQuery) ->
            if (index > 0) sb.append("\n")
            val start = sb.length
            sb.append(label)
            val end = sb.length
            sb.setSpan(
                object : ClickableSpan() {
                    override fun onClick(widget: View) {
                        openSmartSearch(context, urlOrQuery)
                    }

                    override fun updateDrawState(ds: TextPaint) {
                        super.updateDrawState(ds)
                        ds.isUnderlineText = true
                        ds.color = 0xFF1565C0.toInt()
                    }
                },
                start,
                end,
                Spanned.SPAN_EXCLUSIVE_EXCLUSIVE,
            )
        }
        tv.text = sb
        tv.linksClickable = true
        tv.isClickable = true
        tv.isFocusable = true
        tv.movementMethod = LinkMovementMethod.getInstance()
    }
}
