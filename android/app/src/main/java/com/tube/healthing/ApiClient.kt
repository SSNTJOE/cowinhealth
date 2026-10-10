package com.tube.healthing

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
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

    fun login(email: String, password: String): JSONObject {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("email", email)
            .addFormDataPart("password", password)
            .build()
        val req = Request.Builder().url("$baseUrl/api/login").post(body).build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(json.optString("detail", "登入失敗"))
            token = json.getString("token")
            return json
        }
    }

    fun me(): JSONObject {
        val req = Request.Builder().url("$baseUrl/api/me").auth().get().build()
        client.newCall(req).execute().use { resp ->
            return JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
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
        if (pulseJson != null) builder.addFormDataPart("pulse_json", pulseJson)
        val jpeg = "image/jpeg".toMediaType()
        if (face != null) builder.addFormDataPart("face", "face.jpg", face.asRequestBody(jpeg))
        if (tongue != null) builder.addFormDataPart("tongue", "tongue.jpg", tongue.asRequestBody(jpeg))
        val req = Request.Builder().url("$baseUrl/api/record").auth().post(builder.build()).build()
        client.newCall(req).execute().use { resp ->
            val json = JSONObject(resp.body?.string().orEmpty().ifBlank { "{}" })
            if (!resp.isSuccessful) throw RuntimeException(json.optString("detail", "送出失敗"))
            return json
        }
    }

    private fun Request.Builder.auth(): Request.Builder {
        if (!token.isNullOrBlank()) header("Authorization", "Bearer $token")
        return this
    }
}
