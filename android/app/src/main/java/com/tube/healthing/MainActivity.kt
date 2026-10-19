package com.tube.healthing

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.text.method.LinkMovementMethod
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import com.tube.healthing.databinding.ActivityMainBinding
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private val api = ApiClient("http://10.0.2.2:8000")
    private var imageCapture: ImageCapture? = null
    private var faceFile: File? = null
    private var tongueFile: File? = null
    private var pulseJson: String? = null
    private var female = false
    private val cameraExecutor = Executors.newSingleThreadExecutor()
    private val http = okhttp3.OkHttpClient()

    private val permission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> if (granted) startCamera() }

    private val pulseLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            pulseJson = result.data?.getStringExtra("pulse_json")
            binding.result.text = "脈診完成：$pulseJson"
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        HealthFlags.inflate(binding.conditionsGroup, HealthFlags.CONDITIONS)
        HealthFlags.inflate(binding.allergiesGroup, HealthFlags.ALLERGIES)
        binding.result.movementMethod = LinkMovementMethod.getInstance()
        val bmiWatcher = object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                refreshBmi()
            }
        }
        binding.height.addTextChangedListener(bmiWatcher)
        binding.weight.addTextChangedListener(bmiWatcher)
        refreshBmi()

        binding.login.setOnClickListener { Thread { login() }.start() }
        binding.register.setOnClickListener { Thread { register() }.start() }
        binding.saveProfile.setOnClickListener {
            val nickname = binding.nickname.text.toString()
            val birthYear = binding.birthYear.text.toString()
            val gender = selectedGender()
            val height = binding.height.text.toString()
            val weight = binding.weight.text.toString()
            val conditions = HealthFlags.selectedJson(binding.conditionsGroup)
            val allergies = HealthFlags.selectedJson(binding.allergiesGroup)
            Thread {
                saveProfile(nickname, birthYear, gender, height, weight, conditions, allergies)
            }.start()
        }
        binding.shotFace.setOnClickListener { capture("face") }
        binding.shotTongue.setOnClickListener { capture("tongue") }
        binding.openPulse.setOnClickListener {
            pulseLauncher.launch(Intent(this, PulseActivity::class.java))
        }
        binding.save.setOnClickListener { Thread { save() }.start() }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED
        ) startCamera() else permission.launch(Manifest.permission.CAMERA)
    }

    private fun login() {
        try {
            api.setBaseUrl(binding.server.text.toString())
            api.login(
                binding.email.text.toString(),
                binding.password.text.toString()
            )
            val me = api.me()
            runOnUiThread {
                applyUser(me.optJSONObject("user"))
                Toast.makeText(this, "已登入，資料來自 MySQL", Toast.LENGTH_SHORT).show()
            }
            refreshTrend()
        } catch (e: Exception) {
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    private fun register() {
        try {
            api.setBaseUrl(binding.server.text.toString())
            val json = api.register(
                binding.email.text.toString(),
                binding.password.text.toString()
            )
            val me = api.me()
            runOnUiThread {
                applyUser(me.optJSONObject("user") ?: JSONObject().put("user_id", json.optString("user_id")))
                Toast.makeText(this, "已在 MySQL 建立帳號，請補齊基本資料後儲存", Toast.LENGTH_LONG).show()
            }
            refreshTrend()
        } catch (e: Exception) {
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    private fun applyUser(user: JSONObject?) {
        if (user == null) return
        binding.anon.text = "匿名 ID：" + user.optString("user_id")
        binding.nickname.setText(jsonText(user, "nickname"))
        binding.birthYear.setText(jsonText(user, "birth_year"))
        binding.height.setText(jsonText(user, "height"))
        binding.weight.setText(jsonText(user, "weight"))
        when (jsonText(user, "gender")) {
            "female" -> binding.genderFemale.isChecked = true
            "male" -> binding.genderMale.isChecked = true
            "other" -> binding.genderOther.isChecked = true
            else -> binding.genderGroup.clearCheck()
        }
        HealthFlags.apply(binding.conditionsGroup, user.optJSONArray("conditions"))
        HealthFlags.apply(binding.allergiesGroup, user.optJSONArray("allergies"))
        female = jsonText(user, "gender") == "female"
        loadBodyImage()
        refreshBmi()
    }

    private fun refreshBmi() {
        binding.bmiLive.text = Bmi.formatDisplay(
            binding.height.text.toString(),
            binding.weight.text.toString()
        )
    }

    private fun jsonText(user: JSONObject, key: String): String {
        if (!user.has(key) || user.isNull(key)) return ""
        val value = user.opt(key) ?: return ""
        val text = value.toString()
        return if (text == "null") "" else text
    }

    private fun selectedGender(): String {
        return when (binding.genderGroup.checkedRadioButtonId) {
            binding.genderFemale.id -> "female"
            binding.genderMale.id -> "male"
            binding.genderOther.id -> "other"
            else -> ""
        }
    }

    private fun startCamera() {
        // ScrollView + SurfaceView makes the emulator scale a tiny camera buffer into blocks.
        binding.preview.implementationMode = PreviewView.ImplementationMode.COMPATIBLE
        val selector = CameraBind.resolution()
        val providerFuture = ProcessCameraProvider.getInstance(this)
        providerFuture.addListener({
            try {
                val provider = providerFuture.get()
                val preview = Preview.Builder()
                    .setResolutionSelector(selector)
                    .build()
                    .also { it.setSurfaceProvider(binding.preview.surfaceProvider) }
                imageCapture = ImageCapture.Builder()
                    .setResolutionSelector(selector)
                    .build()
                val capture = imageCapture
                if (capture == null || CameraBind.bind(
                        this,
                        provider,
                        CameraSelector.DEFAULT_FRONT_CAMERA,
                        preview,
                        capture
                    ) == null
                ) {
                    imageCapture = null
                    Toast.makeText(this, "模擬器沒有可用鏡頭，請把 Camera 設成 VirtualScene 或 Webcam", Toast.LENGTH_LONG).show()
                }
            } catch (e: Exception) {
                imageCapture = null
                Toast.makeText(this, e.message ?: "無法開啟鏡頭", Toast.LENGTH_LONG).show()
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun capture(kind: String) {
        val capture = imageCapture ?: return
        val file = File(cacheDir, "$kind.jpg")
        val options = ImageCapture.OutputFileOptions.Builder(file).build()
        capture.takePicture(
            options,
            cameraExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(outputFileResults: ImageCapture.OutputFileResults) {
                    if (kind == "face") faceFile = file else tongueFile = file
                    runOnUiThread { Toast.makeText(this@MainActivity, "已拍$kind", Toast.LENGTH_SHORT).show() }
                }
                override fun onError(exception: ImageCaptureException) {
                    runOnUiThread { Toast.makeText(this@MainActivity, exception.message, Toast.LENGTH_LONG).show() }
                }
            }
        )
    }

    private fun saveProfile(
        nickname: String,
        birthYear: String,
        gender: String,
        height: String,
        weight: String,
        conditionsJson: String,
        allergiesJson: String
    ) {
        try {
            api.setBaseUrl(binding.server.text.toString())
            api.updateProfile(nickname, birthYear, gender, height, weight, conditionsJson, allergiesJson)
            val me = api.me()
            runOnUiThread {
                applyUser(me.optJSONObject("user"))
                Toast.makeText(this, "已寫入 MySQL，網站與 App 會看到同一份資料", Toast.LENGTH_SHORT).show()
            }
        } catch (e: Exception) {
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    private fun save() {
        try {
            val json = api.submit(
                binding.symptoms.text.toString(),
                binding.discomfort.text.toString(),
                faceFile,
                tongueFile,
                pulseJson
            )
            runOnUiThread {
                binding.result.text = pretty(json)
                refreshTrend()
                binding.bodyImage.post {
                    Thread {
                        applyBodyOverlays(
                            binding.bodyMap,
                            binding.bodyImage,
                            json.optJSONObject("overlays"),
                            female,
                            api::mediaUrl,
                            http
                        )
                    }.start()
                }
            }
        } catch (e: Exception) {
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    private fun loadBodyImage() {
        val name = if (female) "girl-body.png" else "boy-body.png"
        Thread {
            try {
                val req = okhttp3.Request.Builder().url(api.mediaUrl(name)).build()
                http.newCall(req).execute().use { resp ->
                    val bytes = resp.body?.bytes() ?: return@use
                    val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                    runOnUiThread { binding.bodyImage.setImageBitmap(bmp) }
                }
            } catch (_: Exception) {
            }
        }.start()
    }

    private fun refreshTrend() {
        Thread {
            try {
                val data = api.records()
                runOnUiThread { TrendCharts.bind(binding.trendChart, data.optJSONObject("trend")) }
            } catch (_: Exception) {
            }
        }.start()
    }

    private fun pretty(json: JSONObject): String {
        val scores = json.optJSONObject("scores")
        val patterns = json.optJSONObject("patterns")
        return "匿名紀錄已寫入 MySQL（教學參考，非診斷）\n" +
            "食療：" + json.optString("diet_advice") + "\n" +
            "食療搜尋：" + json.optString("diet_url") + "\n" +
            "穴道搜尋：" + json.optString("acupoint_url") + "\n" +
            "分數：" + scores + "\n" +
            "證型：" + patterns
    }
}
