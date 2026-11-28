package com.tube.healthing

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.util.Log
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.ConnectException
import java.net.InetAddress
import java.net.Socket
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.util.concurrent.TimeUnit
import javax.net.SocketFactory

class ApiClient(
    private var baseUrl: String,
    private var token: String? = null,
    context: Context? = null,
) {
    private val appContext = context?.applicationContext

    private fun buildClient(
        connectSec: Long,
        readSec: Long,
        writeSec: Long = readSec,
        callSec: Long,
    ): OkHttpClient {
        val b = OkHttpClient.Builder()
            .connectTimeout(connectSec, TimeUnit.SECONDS)
            .readTimeout(readSec, TimeUnit.SECONDS)
            .writeTimeout(writeSec, TimeUnit.SECONDS)
            .callTimeout(callSec, TimeUnit.SECONDS)
        // Dual Wi‑Fi+cellular phones often try LAN IPs via the cellular interface
        // (e.g. src 10.x → 192.168.x fails). Prefer Wi‑Fi sockets for API calls.
        val wifiFactory = appContext?.let { WifiPreferSocketFactory(it) }
        if (wifiFactory != null) {
            b.socketFactory(wifiFactory)
        }
        // Align Accept-Language + country/currency with App UI lang on every call.
        val ctx = appContext
        if (ctx != null) {
            b.addInterceptor(LocaleHeaderInterceptor(ctx))
        }
        return b.build()
    }

    private val client = buildClient(connectSec = 12, readSec = 30, callSec = 60)

    /**
     * Country recipe pages can still be large; give the list call more headroom than
     * the default 30s read so a slow first page does not leave the dropdown empty.
     */
    private val recipesClient = buildClient(
        connectSec = 12,
        readSec = 60,
        writeSec = 30,
        callSec = 90,
    )

    /**
     * Captcha is a tiny JSON+PNG payload. Keep connect short so wrong host / loopback
     * fails fast with CAPTCHA_REFUSED or CAPTCHA_TIMEOUT instead of hanging the login UI.
     */
    private val captchaClient = buildClient(
        connectSec = 8,
        readSec = 20,
        writeSec = 15,
        callSec = 30,
    )

    /**
     * /api/record can run stool/urine Lab + day merge; phone uploads need headroom.
     * Short read timeouts left circle UI stuck on the previous judgment line.
     */
    private val recordClient = buildClient(
        connectSec = 20,
        readSec = 90,
        writeSec = 60,
        callSec = 120,
    )

    /** Circle-only: small JPEG + server fast path; tighter than full face/tongue record. */
    private val circleClient = buildClient(
        connectSec = 12,
        readSec = 45,
        writeSec = 30,
        callSec = 60,
    )

    /** Recipe research/create can take minutes; keep a longer client for ensure only. */
    private val ensureClient = buildClient(
        connectSec = 20,
        readSec = 180,
        writeSec = 60,
        callSec = 240,
    )

    fun setBaseUrl(url: String) {
        baseUrl = url.trimEnd('/')
    }

    /**
     * SocketFactory that opens sockets on the active Wi‑Fi [Network] when available.
     * Falls back to the platform default (so emulator / Wi‑Fi-only still works).
     */
    private class WifiPreferSocketFactory(
        private val app: Context,
    ) : SocketFactory() {
        private val fallback = getDefault()

        private fun wifiSocketFactory(): SocketFactory {
            val cm = app.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
                ?: return fallback
            var best: Network? = null
            for (network in cm.allNetworks) {
                val caps = cm.getNetworkCapabilities(network) ?: continue
                if (!caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) continue
                best = network
                // Prefer validated Wi‑Fi when present.
                if (caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)) {
                    return network.socketFactory
                }
            }
            return best?.socketFactory ?: fallback
        }

        private fun factory(): SocketFactory = try {
            wifiSocketFactory()
        } catch (_: Exception) {
            fallback
        }

        override fun createSocket(): Socket = factory().createSocket()

        override fun createSocket(host: String?, port: Int): Socket =
            factory().createSocket(host, port)

        override fun createSocket(host: String?, port: Int, localHost: InetAddress?, localPort: Int): Socket =
            factory().createSocket(host, port, localHost, localPort)

        override fun createSocket(host: InetAddress?, port: Int): Socket =
            factory().createSocket(host, port)

        override fun createSocket(
            address: InetAddress?,
            port: Int,
            localAddress: InetAddress?,
            localPort: Int,
        ): Socket = factory().createSocket(address, port, localAddress, localPort)
    }

    fun hasToken(): Boolean = !token.isNullOrBlank()

    fun mediaUrl(name: String): String = "$baseUrl/media/$name"

    fun captcha(): JSONObject {
        val url = "$baseUrl/api/captcha"
        Log.i(TAG, "GET $url (captchaClient connect=8s read=20s)")
        val req = Request.Builder().url(url).get().build()
        try {
            captchaClient.newCall(req).execute().use { resp ->
                val body = resp.body?.string().orEmpty()
                Log.i(TAG, "captcha HTTP ${resp.code} bytes=${body.length}")
                val json = JSONObject(body.ifBlank { "{}" })
                if (!resp.isSuccessful) {
                    throw RuntimeException(errorDetail(json, "取得驗證碼失敗 HTTP ${resp.code}"))
                }
                val token = json.optString("captcha_token")
                val b64 = json.optString("image_base64")
                val mime = json.optString("mime", "image/png")
                Log.i(
                    TAG,
                    "captcha fields tokenLen=${token.length} b64Len=${b64.length} mime=$mime keys=${json.keys().asSequence().toList()}"
                )
                if (token.isBlank() || b64.isBlank()) {
                    throw RuntimeException("CAPTCHA_BAD_JSON: missing captcha_token or image_base64")
                }
                return json
            }
        } catch (e: UnknownHostException) {
            throw IOException("CAPTCHA_DNS: ${e.message}", e)
        } catch (e: ConnectException) {
            throw IOException("CAPTCHA_REFUSED: ${e.message}", e)
        } catch (e: SocketTimeoutException) {
            throw IOException("CAPTCHA_TIMEOUT: ${e.message}", e)
        } catch (e: IOException) {
            val msg = (e.message ?: "").lowercase()
            if (msg.contains("cleartext") || msg.contains("plaintext")) {
                throw IOException("CAPTCHA_CLEARTEXT: ${e.message}", e)
            }
            // Android often wraps refused LAN routes as "Failed to connect to /x.x.x.x:8000"
            if (msg.contains("failed to connect") || msg.contains("connection refused") ||
                msg.contains("econnrefused")
            ) {
                throw IOException("CAPTCHA_REFUSED: ${e.message}", e)
            }
            throw e
        }
    }

    companion object {
        private const val TAG = "HealthingCaptcha"
    }

    fun register(
        email: String,
        password: String,
        captchaToken: String,
        captchaAnswer: String,
        websiteUrl: String = "",
    ): JSONObject {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("email", email)
            .addFormDataPart("password", password)
            .addFormDataPart("captcha_token", captchaToken)
            .addFormDataPart("captcha_answer", captchaAnswer)
            .addFormDataPart("website_url", websiteUrl)
            .build()
        val req = Request.Builder().url("$baseUrl/api/register").post(body).build()
        return executeAuth(req, "註冊失敗")
    }

    fun login(
        email: String,
        password: String,
        captchaToken: String,
        captchaAnswer: String,
        websiteUrl: String = "",
    ): JSONObject {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("email", email)
            .addFormDataPart("password", password)
            .addFormDataPart("captcha_token", captchaToken)
            .addFormDataPart("captcha_answer", captchaAnswer)
            .addFormDataPart("website_url", websiteUrl)
            .build()
        val req = Request.Builder().url("$baseUrl/api/login").post(body).build()
        return executeAuth(req, "登入失敗")
    }

    fun records(): JSONObject {
        val req = Request.Builder().url("$baseUrl/api/records").auth().get().build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "讀取歷史紀錄失敗"))
            return json
        }
    }

    fun flags(lang: String? = null): JSONObject {
        val url = "$baseUrl/api/flags".toHttpUrl().newBuilder().apply {
            if (!lang.isNullOrBlank()) addQueryParameter("lang", lang)
        }.build()
        val req = Request.Builder().url(url).get().build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "讀取過敏選項失敗"))
            return json
        }
    }

    fun affiliates(category: String? = null): JSONObject {
        val url = if (category.isNullOrBlank()) {
            "$baseUrl/api/affiliates"
        } else {
            "$baseUrl/api/affiliates?category=${java.net.URLEncoder.encode(category, "UTF-8")}"
        }
        val req = Request.Builder().url(url).get().build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "讀取導購推薦失敗"))
            return json
        }
    }

    fun me(): JSONObject {
        val req = Request.Builder().url("$baseUrl/api/me").auth().get().build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "讀取個人資料失敗"))
            return json
        }
    }

    fun updateProfile(
        nickname: String,
        birthYear: String,
        gender: String,
        height: String,
        weight: String,
        conditionsJson: String,
        allergiesJson: String,
        preferredLang: String = "",
    ): JSONObject {
        val builder = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("conditions_json", conditionsJson)
            .addFormDataPart("allergies_json", allergiesJson)
        if (nickname.isNotBlank()) builder.addFormDataPart("nickname", nickname)
        if (birthYear.isNotBlank()) builder.addFormDataPart("birth_year", birthYear)
        if (gender.isNotBlank()) builder.addFormDataPart("gender", gender)
        if (height.isNotBlank()) builder.addFormDataPart("height", height)
        if (weight.isNotBlank()) builder.addFormDataPart("weight", weight)
        if (preferredLang.isNotBlank()) builder.addFormDataPart("preferred_lang", preferredLang)
        val req = Request.Builder().url("$baseUrl/api/profile").auth().post(builder.build()).build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "儲存基本資料失敗"))
            return json
        }
    }

    fun updatePreferredLang(lang: String): JSONObject {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("preferred_lang", lang)
            .build()
        val req = Request.Builder().url("$baseUrl/api/profile").auth().post(body).build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "儲存語言偏好失敗"))
            return json
        }
    }

    fun recipeCountries(
        lang: String,
        scores: String,
        patterns: String,
        female: Boolean,
        byBody: Boolean = false
    ): JSONObject {
        val url = "$baseUrl/api/recipes/countries".toHttpUrl().newBuilder()
            .addQueryParameter("lang", lang)
            .addQueryParameter("female", if (female) "1" else "0")
            .addQueryParameter("by_body", if (byBody) "1" else "0")
        if (scores.isNotBlank()) url.addQueryParameter("scores", scores)
        if (patterns.isNotBlank()) url.addQueryParameter("patterns", patterns)
        val req = Request.Builder().url(url.build()).auth().get().build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "讀取國家列表失敗"))
            return json
        }
    }

    fun recipes(
        country: String,
        lang: String,
        scores: String,
        patterns: String,
        female: Boolean,
        byBody: Boolean = false,
        name: String = "",
        limit: Int? = 80,
        offset: Int = 0,
    ): JSONObject {
        val url = "$baseUrl/api/recipes".toHttpUrl().newBuilder()
            .addQueryParameter("lang", lang)
            .addQueryParameter("female", if (female) "1" else "0")
            .addQueryParameter("by_body", if (byBody) "1" else "0")
            .addQueryParameter("offset", offset.coerceAtLeast(0).toString())
        val countryTrim = country.trim()
        val nameTrim = name.trim()
        if (countryTrim.isNotEmpty()) url.addQueryParameter("country", countryTrim)
        if (nameTrim.isNotEmpty()) url.addQueryParameter("name", nameTrim)
        if (scores.isNotBlank()) url.addQueryParameter("scores", scores)
        if (patterns.isNotBlank()) url.addQueryParameter("patterns", patterns)
        if (limit != null) url.addQueryParameter("limit", limit.coerceIn(1, 500).toString())
        val req = Request.Builder().url(url.build()).auth().get().build()
        recipesClient.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "讀取食譜失敗"))
            return json
        }
    }

    fun submit(
        symptoms: String,
        discomfort: String,
        face: File?,
        tongue: File?,
        pulseJson: String?,
        colorTemperatureK: String = "auto",
        shotType: String? = null,
        shotFile: File? = null,
        confounders: String? = null,
        includePulse: Boolean = true,
        deviceHint: String? = null,
    ): JSONObject {
        val builder = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("symptoms", symptoms)
            .addFormDataPart("discomfort", discomfort)
            .addFormDataPart("include_pulse", if (includePulse) "1" else "0")
            .addFormDataPart("color_temperature_k", colorTemperatureK)
        if (pulseJson != null) builder.addFormDataPart("pulse_json", pulseJson)
        if (!confounders.isNullOrBlank()) builder.addFormDataPart("confounders", confounders)
        if (!deviceHint.isNullOrBlank()) builder.addFormDataPart("device_hint", deviceHint)
        val jpeg = "image/jpeg".toMediaType()
        if (face != null) builder.addFormDataPart("face", "face.jpg", face.asRequestBody(jpeg))
        if (tongue != null) builder.addFormDataPart("tongue", "tongue.jpg", tongue.asRequestBody(jpeg))
        // Same MySQL path as website: shot_type + image for stool/urine (text-only teaching).
        if (!shotType.isNullOrBlank() && shotFile != null) {
            builder.addFormDataPart("shot_type", shotType)
            builder.addFormDataPart("image", "$shotType.jpg", shotFile.asRequestBody(jpeg))
        }
        val req = Request.Builder().url("$baseUrl/api/record").auth().post(builder.build()).build()
        recordClient.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "送出失敗"))
            return json
        }
    }

    /**
     * Stool/urine only: no face/tongue/pulse upload, `circle_fast=1` so server skips
     * week-advice + deviation xls. Judgment text still waits for this response.
     */
    fun submitCircle(
        symptoms: String,
        discomfort: String,
        colorTemperatureK: String = "auto",
        shotType: String,
        shotFile: File,
        deviceHint: String? = null,
    ): JSONObject {
        val jpeg = "image/jpeg".toMediaType()
        val builder = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("symptoms", symptoms)
            .addFormDataPart("discomfort", discomfort)
            .addFormDataPart("include_pulse", "0")
            .addFormDataPart("color_temperature_k", colorTemperatureK)
            .addFormDataPart("circle_fast", "1")
            .addFormDataPart("shot_type", shotType)
            .addFormDataPart("image", "$shotType.jpg", shotFile.asRequestBody(jpeg))
        if (!deviceHint.isNullOrBlank()) builder.addFormDataPart("device_hint", deviceHint)
        val req = Request.Builder().url("$baseUrl/api/record").auth().post(builder.build()).build()
        circleClient.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "送出失敗"))
            return json
        }
    }

    fun mealsDay(date: String? = null): JSONObject {
        val url = "$baseUrl/api/meals/day".toHttpUrl().newBuilder()
        if (!date.isNullOrBlank()) url.addQueryParameter("date", date)
        val req = Request.Builder().url(url.build()).auth().get().build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "讀取飲食日摘要失敗"))
            return json
        }
    }

    fun mealsMonth(year: Int, month: Int): JSONObject {
        val url = "$baseUrl/api/meals/month".toHttpUrl().newBuilder()
            .addQueryParameter("year", year.toString())
            .addQueryParameter("month", month.toString())
            .build()
        val req = Request.Builder().url(url).auth().get().build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "讀取飲食月曆失敗"))
            return json
        }
    }

    fun addMeal(
        recipeId: Int,
        mealDate: String,
        mealSlot: String,
        servings: Double = 1.0,
        lang: String = "zh",
    ): JSONObject {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("recipe_id", recipeId.toString())
            .addFormDataPart("meal_date", mealDate)
            .addFormDataPart("meal_slot", mealSlot)
            .addFormDataPart("servings", servings.toString())
            .addFormDataPart("lang", lang)
            .build()
        val req = Request.Builder().url("$baseUrl/api/meals").auth().post(body).build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "加入飲食失敗"))
            return json
        }
    }

    fun deleteMeal(mealId: Int, date: String? = null): JSONObject {
        val url = "$baseUrl/api/meals/$mealId".toHttpUrl().newBuilder()
        if (!date.isNullOrBlank()) url.addQueryParameter("date", date)
        val req = Request.Builder().url(url.build()).auth().delete().build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "刪除飲食失敗"))
            return json
        }
    }

    fun activityToday(date: String? = null): JSONObject {
        val url = "$baseUrl/api/activity/today".toHttpUrl().newBuilder()
        if (!date.isNullOrBlank()) url.addQueryParameter("date", date)
        val req = Request.Builder().url(url.build()).auth().get().build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "讀取今日活動失敗"))
            return json
        }
    }

    fun postSteps(
        date: String,
        actualSteps: Int,
        source: String,
        burnedKcal: Double? = null,
    ): JSONObject {
        val builder = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("date", date)
            .addFormDataPart("actual_steps", actualSteps.toString())
            .addFormDataPart("steps", actualSteps.toString())
            .addFormDataPart("source", source)
        if (burnedKcal != null) {
            builder.addFormDataPart("burned_kcal", burnedKcal.toString())
        }
        val req = Request.Builder().url("$baseUrl/api/activity/today").auth().post(builder.build()).build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "同步步數失敗"))
            return json
        }
    }

    /** Create / research a recipe into Recipe.xls via the same API the website uses. */
    fun ensureRecipe(country: String, name: String, lang: String): JSONObject {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("country", country)
            .addFormDataPart("name", name)
            .addFormDataPart("lang", lang)
            .build()
        val req = Request.Builder().url("$baseUrl/api/recipes/ensure").auth().post(body).build()
        ensureClient.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "建立食譜失敗"))
            return json
        }
    }

    private fun executeAuth(req: Request, fallback: String): JSONObject {
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, fallback))
            token = json.getString("token")
            return json
        }
    }

    private fun Request.Builder.auth(): Request.Builder {
        if (!token.isNullOrBlank()) header("Authorization", "Bearer $token")
        return this
    }

    private fun errorDetail(json: JSONObject, fallback: String): String {
        return when (val detail = json.opt("detail")) {
            is String -> detail.ifBlank { fallback }
            is JSONArray -> (0 until detail.length()).joinToString("；") { index ->
                val item = detail.opt(index)
                if (item is JSONObject) item.optString("msg", item.toString()) else item.toString()
            }.ifBlank { fallback }
            else -> fallback
        }
    }
}
