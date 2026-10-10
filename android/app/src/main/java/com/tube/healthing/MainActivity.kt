package com.tube.healthing

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.os.Bundle
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
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

        binding.login.setOnClickListener { Thread { login() }.start() }
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
            val json = api.login(
                binding.email.text.toString(),
                binding.password.text.toString()
            )
            val me = api.me()
            val user = me.optJSONObject("user")
            female = user?.optString("gender") == "female"
            runOnUiThread {
                binding.anon.text = "匿名 ID：" + json.getString("user_id")
                loadBodyImage()
            }
        } catch (e: Exception) {
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    private fun startCamera() {
        val providerFuture = ProcessCameraProvider.getInstance(this)
        providerFuture.addListener({
            val provider = providerFuture.get()
            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(binding.preview.surfaceProvider)
            }
            imageCapture = ImageCapture.Builder().build()
            provider.unbindAll()
            provider.bindToLifecycle(
                this,
                CameraSelector.DEFAULT_FRONT_CAMERA,
                preview,
                imageCapture
            )
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

    private fun pretty(json: JSONObject): String {
        val scores = json.optJSONObject("scores")
        val patterns = json.optJSONObject("patterns")
        return "匿名紀錄已寫入 MySQL\n" +
            "食療：" + json.optString("diet_advice") + "\n" +
            "分數：" + scores + "\n" +
            "證型：" + patterns
    }
}
