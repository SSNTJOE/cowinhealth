package com.tube.healthing

import android.content.Context
import android.content.res.Configuration
import android.os.LocaleList
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.os.LocaleListCompat
import java.util.Locale

/**
 * App UI language: zh / en / ja / ko.
 *
 * - No explicit choice → follow system locale (Android resources auto).
 * - Manual switch → [AppCompatDelegate.setApplicationLocales] (Android 13+
 *   Per-App Language Preferences + AppCompat storage on older APIs).
 */
object AppLocale {
    const val PREFS = "healthing"
    const val KEY_UI_LANG = "ui_lang"
    const val KEY_EXPLICIT = "ui_lang_explicit"
    const val KEY_SUGGEST_ACK = "lang_suggest_ack"

    val supported = listOf("zh", "en", "ja", "ko")

    fun bcp47(code: String): String = when (normalize(code)) {
        "zh" -> "zh-TW"
        "en" -> "en"
        "ja" -> "ja"
        "ko" -> "ko"
        else -> "zh-TW"
    }

    fun normalize(code: String?): String {
        val raw = (code ?: "").trim().lowercase(Locale.ROOT)
        return when {
            raw in supported -> raw
            raw.startsWith("zh") -> "zh"
            raw.startsWith("en") -> "en"
            raw.startsWith("ja") -> "ja"
            raw.startsWith("ko") -> "ko"
            else -> "zh"
        }
    }

    fun fromTag(tag: String?): String? {
        val raw = (tag ?: "").trim().lowercase(Locale.ROOT).replace('_', '-')
        if (raw.isBlank()) return null
        val primary = raw.substringBefore('-')
        return when (primary) {
            "zh", "en", "ja", "ko" -> primary
            else -> null
        }
    }

    fun country(code: String): String = when (normalize(code)) {
        "en" -> "US"
        "ja" -> "JP"
        "ko" -> "KR"
        else -> "TW"
    }

    fun currency(code: String): String = when (normalize(code)) {
        "en" -> "USD"
        "ja" -> "JPY"
        "ko" -> "KRW"
        else -> "TWD"
    }

    fun acceptLanguage(code: String): String = when (normalize(code)) {
        "en" -> "en,en-US;q=0.9"
        "ja" -> "ja,en;q=0.6"
        "ko" -> "ko,en;q=0.6"
        else -> "zh-TW,zh;q=0.9,en;q=0.5"
    }

    fun deviceUiLang(): String? = fromTag(Locale.getDefault().toLanguageTag())
        ?: fromTag(Locale.getDefault().language)

    fun currentUiLang(context: Context): String {
        val appLocales = AppCompatDelegate.getApplicationLocales()
        if (!appLocales.isEmpty) {
            fromTag(appLocales.get(0)?.toLanguageTag())?.let { return it }
        }
        deviceUiLang()?.let { return it }
        val stored = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_UI_LANG, null)
        if (stored in supported) return stored!!
        return "zh"
    }

    fun isExplicit(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(KEY_EXPLICIT, false)

    /** Apply a manual (or server preferred) UI language via per-app locales. */
    fun applyUiLang(context: Context, code: String, explicit: Boolean = true) {
        val normalized = normalize(code)
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(KEY_UI_LANG, normalized)
            .putBoolean(KEY_EXPLICIT, explicit)
            .apply()
        AppCompatDelegate.setApplicationLocales(
            LocaleListCompat.forLanguageTags(bcp47(normalized)),
        )
    }

    /** Clear per-app override so Android resources follow the system locale. */
    fun followSystem(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putBoolean(KEY_EXPLICIT, false)
            .apply()
        AppCompatDelegate.setApplicationLocales(LocaleListCompat.getEmptyLocaleList())
    }

    /**
     * On cold start: restore an explicit choice (incl. legacy `ui_lang` prefs).
     * Otherwise leave empty locales → system auto.
     */
    fun bootstrap(context: Context) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val stored = prefs.getString(KEY_UI_LANG, null)
        val hasExplicitKey = prefs.contains(KEY_EXPLICIT)
        val explicit = prefs.getBoolean(KEY_EXPLICIT, false)
        when {
            explicit && stored in supported -> {
                AppCompatDelegate.setApplicationLocales(
                    LocaleListCompat.forLanguageTags(bcp47(stored!!)),
                )
            }
            !hasExplicitKey && stored in supported -> {
                // Legacy installs treated saved ui_lang as an explicit choice.
                prefs.edit().putBoolean(KEY_EXPLICIT, true).apply()
                AppCompatDelegate.setApplicationLocales(
                    LocaleListCompat.forLanguageTags(bcp47(stored!!)),
                )
            }
            else -> {
                // System locale auto (resources + Configuration).
                AppCompatDelegate.setApplicationLocales(LocaleListCompat.getEmptyLocaleList())
            }
        }
    }

    fun contextFor(base: Context, lang: String): Context {
        val locale = Locale.forLanguageTag(bcp47(lang))
        val config = Configuration(base.resources.configuration)
        config.setLocales(LocaleList(locale))
        return base.createConfigurationContext(config)
    }

    fun displayLabel(context: Context, code: String): String {
        val ctx = contextFor(context, normalize(code))
        val resName = when (normalize(code)) {
            "en" -> "lang_en"
            "ja" -> "lang_ja"
            "ko" -> "lang_ko"
            else -> "lang_zh"
        }
        val id = ctx.resources.getIdentifier(resName, "string", ctx.packageName)
        if (id != 0) return ctx.getString(id)
        return when (normalize(code)) {
            "en" -> "English"
            "ja" -> "日本語"
            "ko" -> "한국어"
            else -> "中文"
        }
    }
}
