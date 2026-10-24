package com.tube.healthing

import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

class ApiClient(
    private var baseUrl: String,
    private var token: String? = null
) {
    private val client = OkHttpClient.Builder()
        .callTimeout(60, TimeUnit.SECONDS)
        .build()

    fun setBaseUrl(url: String) {
        baseUrl = url.trimEnd('/')
    }

    fun mediaUrl(name: String): String = "$baseUrl/media/$name"

    fun register(email: String, password: String): JSONObject {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("email", email)
            .addFormDataPart("password", password)
            .build()
        val req = Request.Builder().url("$baseUrl/api/register").post(body).build()
        return executeAuth(req, "註冊失敗")
    }

    fun login(email: String, password: String): JSONObject {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("email", email)
            .addFormDataPart("password", password)
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

    fun flags(): JSONObject {
        val req = Request.Builder().url("$baseUrl/api/flags").get().build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "讀取過敏選項失敗"))
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
        allergiesJson: String
    ): JSONObject {
        val builder = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("conditions_json", conditionsJson)
            .addFormDataPart("allergies_json", allergiesJson)
        if (nickname.isNotBlank()) builder.addFormDataPart("nickname", nickname)
        if (birthYear.isNotBlank()) builder.addFormDataPart("birth_year", birthYear)
        if (gender.isNotBlank()) builder.addFormDataPart("gender", gender)
        if (height.isNotBlank()) builder.addFormDataPart("height", height)
        if (weight.isNotBlank()) builder.addFormDataPart("weight", weight)
        val req = Request.Builder().url("$baseUrl/api/profile").auth().post(builder.build()).build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "儲存基本資料失敗"))
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
        byBody: Boolean = false
    ): JSONObject {
        val url = "$baseUrl/api/recipes".toHttpUrl().newBuilder()
            .addQueryParameter("country", country)
            .addQueryParameter("lang", lang)
            .addQueryParameter("female", if (female) "1" else "0")
            .addQueryParameter("by_body", if (byBody) "1" else "0")
        if (scores.isNotBlank()) url.addQueryParameter("scores", scores)
        if (patterns.isNotBlank()) url.addQueryParameter("patterns", patterns)
        val req = Request.Builder().url(url.build()).auth().get().build()
        client.newCall(req).execute().use { resp ->
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
        pulseJson: String?
    ): JSONObject {
        val builder = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("symptoms", symptoms)
            .addFormDataPart("discomfort", discomfort)
            .addFormDataPart("include_pulse", "1")
        if (pulseJson != null) builder.addFormDataPart("pulse_json", pulseJson)
        val jpeg = "image/jpeg".toMediaType()
        if (face != null) builder.addFormDataPart("face", "face.jpg", face.asRequestBody(jpeg))
        if (tongue != null) builder.addFormDataPart("tongue", "tongue.jpg", tongue.asRequestBody(jpeg))
        val req = Request.Builder().url("$baseUrl/api/record").auth().post(builder.build()).build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(errorDetail(json, "送出失敗"))
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
