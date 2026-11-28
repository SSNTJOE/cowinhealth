package com.tube.healthing

import android.content.Context
import okhttp3.Interceptor
import okhttp3.Response

/**
 * Attach Accept-Language plus country/currency headers aligned with the App UI lang
 * on every OkHttp request.
 */
class LocaleHeaderInterceptor(
    context: Context,
) : Interceptor {
    private val app = context.applicationContext

    override fun intercept(chain: Interceptor.Chain): Response {
        val lang = AppLocale.currentUiLang(app)
        val request = chain.request().newBuilder()
            .header("Accept-Language", AppLocale.acceptLanguage(lang))
            .header("X-App-Lang", lang)
            .header("X-App-Country", AppLocale.country(lang))
            .header("X-App-Currency", AppLocale.currency(lang))
            .build()
        return chain.proceed(request)
    }
}
