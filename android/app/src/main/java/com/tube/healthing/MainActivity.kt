package com.tube.healthing

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.os.Build
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.text.method.LinkMovementMethod
import android.util.Base64
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.AutoCompleteTextView
import android.widget.Filter
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import com.tube.healthing.databinding.ActivityMainBinding
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private val api = ApiClient("http://10.0.2.2:8000")
    private var imageCapture: ImageCapture? = null
    private var faceFile: File? = null
    private var tongueFile: File? = null
    private var stoolFile: File? = null
    private var urineFile: File? = null
    private var alignKind = "face"
    private var pulseJson: String? = null
    private var female = false
    @Volatile private var captchaToken: String = ""
    private val cameraExecutor = Executors.newSingleThreadExecutor()
    private val http = okhttp3.OkHttpClient()
    private val prefs by lazy { getSharedPreferences("healthing", MODE_PRIVATE) }
    private val langCodes = listOf("zh", "en", "ja", "ko")
    private val langLabels = listOf("中文", "English", "日本語", "한국어")
    private val organPatterns = listOf(
        "heart_pattern" to "心",
        "liver_pattern" to "肝",
        "spleen_pattern" to "脾",
        "stomach_pattern" to "胃",
        "lung_pattern" to "肺",
        "kidney_pattern" to "腎",
        "gallbladder_pattern" to "膽",
        "large_intestine_pattern" to "大腸",
        "small_intestine_pattern" to "小腸",
        "bladder_pattern" to "膀胱",
        "uterus_pattern" to "子宮"
    )
    private var recipeRows: List<JSONObject> = emptyList()
    private var countryNames: List<String> = emptyList()
    private var loadedCountry = ""
    private var recipeLoadToken = 0
    private var lastScoresJson = ""
    private var lastPatternsJson = ""
    private var judgmentReady = false
    private var selectedRecipeId = -1
    @Volatile private var recipeShowAllPasses = 0
    private var cameraProvider: ProcessCameraProvider? = null
    private var flagAllergyOptions: List<String> = emptyList()

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
        CameraFacing.ensureDefaults(this)
        binding.preview.implementationMode = PreviewView.ImplementationMode.COMPATIBLE
        binding.preview.scaleType = PreviewView.ScaleType.FILL_CENTER
        binding.server.setText(prefs.getString("base_url", "http://10.0.2.2:8000"))
        binding.result.movementMethod = LinkMovementMethod.getInstance()
        binding.dietLink.movementMethod = LinkMovementMethod.getInstance()
        binding.acupointLink.movementMethod = LinkMovementMethod.getInstance()
        setupLanguageSpinner()
        setupRecipeSpinners()
        applyLangChrome()
        Thread { loadFlagOptions() }.start()
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

        binding.captchaRefresh.setOnClickListener { Thread { refreshCaptcha() }.start() }
        Thread { refreshCaptcha() }.start()
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
        binding.shotFace.setOnClickListener { captureAligned("face") }
        binding.shotTongue.setOnClickListener { captureAligned("tongue") }
        binding.shotStool.setOnClickListener { captureAligned("stool") }
        binding.shotUrine.setOnClickListener { captureAligned("urine") }
        showAlign("face")
        binding.openPulse.setOnClickListener {
            pulseLauncher.launch(Intent(this, PulseActivity::class.java))
        }
        binding.save.setOnClickListener { Thread { save() }.start() }
        binding.recipeEnsure.setOnClickListener { Thread { ensureTypedRecipe() }.start() }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED
        ) {
            permission.launch(Manifest.permission.CAMERA)
        }
    }

    override fun onResume() {
        super.onResume()
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED
        ) {
            startCamera()
        }
    }

    override fun onPause() {
        cameraProvider?.unbindAll()
        imageCapture = null
        super.onPause()
    }

    private fun rememberServer() {
        val url = binding.server.text.toString().trim().trimEnd('/')
        prefs.edit().putString("base_url", url).apply()
        api.setBaseUrl(url)
    }

    private fun refreshCaptcha() {
        try {
            rememberServer()
            val json = api.captcha()
            val token = json.optString("captcha_token")
            val b64 = json.optString("image_base64")
            val bytes = Base64.decode(b64, Base64.DEFAULT)
            val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
            captchaToken = token
            runOnUiThread {
                binding.captchaImage.setImageBitmap(bmp)
                binding.captchaAnswer.setText("")
            }
        } catch (e: Exception) {
            runOnUiThread {
                Toast.makeText(this, e.message ?: t("toastCaptchaFail"), Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun loadFlagOptions() {
        try {
            rememberServer()
            val flags = api.flags()
            runOnUiThread { applyFlagOptions(flags) }
        } catch (_: Exception) {
        }
    }

    private fun login() {
        try {
            rememberServer()
            val answer = binding.captchaAnswer.text.toString().trim()
            val honeypot = binding.websiteUrl.text?.toString().orEmpty()
            if (captchaToken.isBlank() || answer.isBlank()) {
                runOnUiThread { Toast.makeText(this, t("toastNeedCaptcha"), Toast.LENGTH_SHORT).show() }
                return
            }
            api.login(
                binding.email.text.toString(),
                binding.password.text.toString(),
                captchaToken,
                answer,
                honeypot,
            )
            runCatching { api.updatePreferredLang(currentLang()) }
            val me = api.me()
            val flags = flagsOrNull()
            runOnUiThread {
                applyFlagOptions(flags)
                applyUser(me.optJSONObject("user"), flags)
                Toast.makeText(this, t("toastLoggedIn"), Toast.LENGTH_SHORT).show()
                refreshRecipeChoices(keepSelection = false)
            }
            refreshTrend()
            loadLatestAdvice()
            refreshCaptcha()
        } catch (e: Exception) {
            refreshCaptcha()
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    private fun register() {
        try {
            rememberServer()
            val answer = binding.captchaAnswer.text.toString().trim()
            val honeypot = binding.websiteUrl.text?.toString().orEmpty()
            if (captchaToken.isBlank() || answer.isBlank()) {
                runOnUiThread { Toast.makeText(this, t("toastNeedCaptcha"), Toast.LENGTH_SHORT).show() }
                return
            }
            val json = api.register(
                binding.email.text.toString(),
                binding.password.text.toString(),
                captchaToken,
                answer,
                honeypot,
            )
            runCatching { api.updatePreferredLang(currentLang()) }
            val me = api.me()
            val flags = flagsOrNull()
            runOnUiThread {
                applyFlagOptions(flags)
                applyUser(
                    me.optJSONObject("user") ?: JSONObject().put("user_id", json.optString("user_id")),
                    flags
                )
                Toast.makeText(this, t("toastRegistered"), Toast.LENGTH_LONG).show()
                refreshRecipeChoices(keepSelection = false)
            }
            refreshTrend()
            refreshCaptcha()
        } catch (e: Exception) {
            refreshCaptcha()
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    private fun flagsOrNull(): JSONObject? = runCatching { api.flags() }.getOrNull()

    private fun applyFlagOptions(flags: JSONObject?) {
        val keptConditions = JSONArray(HealthFlags.selectedJson(binding.conditionsGroup))
        val keptAllergies = JSONArray(HealthFlags.selectedJson(binding.allergiesGroup))
        val conditions = HealthFlags.jsonLabelsFrom(flags, "conditions")
        if (conditions.isNotEmpty()) {
            HealthFlags.inflate(binding.conditionsGroup, conditions)
            HealthFlags.apply(binding.conditionsGroup, keptConditions)
        }
        val options = HealthFlags.consolidateAllergyOptions(
            HealthFlags.jsonLabelsFrom(flags, "allergy_options", "allergies")
        )
        if (options.isNotEmpty()) {
            flagAllergyOptions = options
            HealthFlags.inflate(binding.allergiesGroup, options)
            HealthFlags.apply(binding.allergiesGroup, keptAllergies)
        }
    }

    private fun applyUser(user: JSONObject?, flags: JSONObject? = null) {
        if (user == null) return
        val preferred = jsonText(user, "preferred_lang")
        if (preferred in langCodes && preferred != currentLang()) {
            prefs.edit().putString("ui_lang", preferred).apply()
            val index = langCodes.indexOf(preferred).coerceAtLeast(0)
            binding.langSelect.setSelection(index)
        }
        binding.anon.text = t("anonPrefix") + user.optString("user_id")
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
        applyLangChrome()
        HealthFlags.apply(binding.conditionsGroup, user.optJSONArray("conditions"))
        val allergyOptions = HealthFlags.consolidateAllergyOptions(
            HealthFlags.jsonLabelsFrom(user, "allergy_options").ifEmpty {
                HealthFlags.jsonLabelsFrom(flags, "allergy_options", "allergies")
            }.ifEmpty { flagAllergyOptions }
        )
        if (allergyOptions.isNotEmpty()) {
            flagAllergyOptions = allergyOptions
            HealthFlags.inflate(binding.allergiesGroup, allergyOptions)
        }
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
        // TextureView works inside ScrollView; SurfaceView (PERFORMANCE) stays black.
        if (!lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) return
        binding.preview.implementationMode = PreviewView.ImplementationMode.COMPATIBLE
        binding.preview.scaleType = PreviewView.ScaleType.FILL_CENTER
        if (!binding.preview.isAttachedToWindow) return
        if (binding.preview.width == 0 || binding.preview.height == 0) {
            binding.preview.post { startCamera() }
            return
        }
        val providerFuture = ProcessCameraProvider.getInstance(this)
        providerFuture.addListener({
            if (!lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) return@addListener
            if (!binding.preview.isAttachedToWindow) return@addListener
            if (binding.preview.width == 0 || binding.preview.height == 0) {
                binding.preview.post { startCamera() }
                return@addListener
            }
            try {
                val provider = providerFuture.get()
                cameraProvider = provider
                var capture: ImageCapture? = null
                var bound = false
                val attempts = buildList {
                    add(null)
                    addAll(CameraBind.trySizes())
                }
                for (size in attempts) {
                    val previewBuilder = Preview.Builder()
                    val captureBuilder = ImageCapture.Builder()
                    if (size != null) {
                        val selector = CameraBind.resolution(size)
                        previewBuilder.setResolutionSelector(selector)
                        captureBuilder.setResolutionSelector(selector)
                    }
                    val preview = previewBuilder.build()
                    capture = captureBuilder.build()
                    if (CameraBind.bindForCaptureKind(
                            this, provider, this, alignKind, preview, capture
                        ) != null
                    ) {
                        preview.setSurfaceProvider(binding.preview.surfaceProvider)
                        applyAlignGuides(alignKind)
                        bound = true
                        break
                    }
                }
                imageCapture = if (bound) capture else null
                if (!bound) {
                    val lens = if (CameraFacing.isFront(this, alignKind)) "前置" else "後置"
                    Toast.makeText(
                        this,
                        "打不開${lens}鏡頭（${alignKind}）。模擬器請檢查 Front/Back camera 設定。",
                        Toast.LENGTH_LONG
                    ).show()
                }
            } catch (e: Exception) {
                imageCapture = null
                Toast.makeText(this, e.message ?: "無法開啟鏡頭", Toast.LENGTH_LONG).show()
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun showAlign(kind: String) {
        val previousFacing = CameraFacing.facingString(this, alignKind)
        alignKind = CameraFacing.normalize(kind)
        applyAlignGuides(alignKind)
        if (previousFacing != CameraFacing.facingString(this, alignKind)) {
            // face/tongue → front; stool/urine → back — rebind when lens changes
            startCamera()
        }
    }

    private fun applyAlignGuides(kind: String) {
        val mode = CameraFacing.normalize(kind)
        val face = mode == CameraFacing.FACE
        val tongue = mode == CameraFacing.TONGUE
        val circle = mode == CameraFacing.STOOL || mode == CameraFacing.URINE
        binding.faceGuide.visibility = if (face) View.VISIBLE else View.GONE
        binding.tongueGuide.visibility = if (tongue) View.VISIBLE else View.GONE
        binding.circleGuide.visibility = if (circle) View.VISIBLE else View.GONE
        // Face + circle shots use ~2× preview zoom (matches website).
        val zoom = when {
            face -> FaceFrame.PREVIEW_ZOOM
            circle -> 2f
            else -> 1f
        }
        binding.preview.scaleX = zoom
        binding.preview.scaleY = zoom
    }

    private fun captureAligned(kind: String) {
        val mode = CameraFacing.normalize(kind)
        if (alignKind != mode) {
            showAlign(mode)
            val message = when (mode) {
                CameraFacing.FACE -> "臉部預覽已放大兩倍，對準黃線後再按一次"
                CameraFacing.TONGUE -> "已切換舌頭黃框，對準後再按一次"
                CameraFacing.STOOL -> "已切換後置鏡頭拍大便，對準後再按一次"
                CameraFacing.URINE -> "已切換後置鏡頭拍尿尿，對準後再按一次"
                else -> "已切換鏡頭，對準後再按一次"
            }
            Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
            return
        }
        capture(mode)
    }

    private fun capture(kind: String) {
        val mode = CameraFacing.normalize(kind)
        val capture = imageCapture ?: run {
            val lens = if (CameraFacing.isFront(this, mode)) "前置" else "後置"
            Toast.makeText(this, "鏡頭尚未就緒（$mode 用${lens}鏡頭）", Toast.LENGTH_SHORT).show()
            return
        }
        val file = File(cacheDir, "$mode.jpg")
        val options = ImageCapture.OutputFileOptions.Builder(file).build()
        val previewW = binding.preview.width
        val previewH = binding.preview.height
        capture.takePicture(
            options,
            cameraExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(outputFileResults: ImageCapture.OutputFileResults) {
                    when (mode) {
                        CameraFacing.FACE -> {
                            try {
                                FaceFrame.cropFileToVisiblePreview(file, previewW, previewH)
                            } catch (_: Exception) {
                            }
                            faceFile = file
                            runOnUiThread {
                                Toast.makeText(this@MainActivity, t("toastFaceShot"), Toast.LENGTH_SHORT).show()
                            }
                        }
                        CameraFacing.TONGUE -> {
                            try {
                                TongueFrame.cropFileToYellowFrame(file, previewW, previewH)
                            } catch (_: Exception) {
                            }
                            tongueFile = file
                            runOnUiThread {
                                Toast.makeText(this@MainActivity, t("toastTongueShot"), Toast.LENGTH_SHORT).show()
                            }
                        }
                        CameraFacing.STOOL, CameraFacing.URINE -> {
                            if (mode == CameraFacing.STOOL) stoolFile = file else urineFile = file
                            // Same as website: analyze immediately; text only, no photo keep/display.
                            Thread { submitCircleShot(mode, file) }.start()
                        }
                    }
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
            rememberServer()
            api.updateProfile(
                nickname,
                birthYear,
                gender,
                height,
                weight,
                conditionsJson,
                allergiesJson,
                preferredLang = currentLang(),
            )
            val me = api.me()
            val flags = flagsOrNull()
            runOnUiThread {
                applyFlagOptions(flags)
                applyUser(me.optJSONObject("user"), flags)
                Toast.makeText(this, t("toastSavedProfile"), Toast.LENGTH_SHORT).show()
                refreshRecipeChoices(keepSelection = true)
            }
        } catch (e: Exception) {
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    private fun pulseReady(raw: String?): Boolean {
        if (raw.isNullOrBlank()) return false
        return try {
            val json = org.json.JSONObject(raw)
            listOf(
                "left_cun_heavy", "left_cun_light",
                "left_guan_heavy", "left_guan_light",
                "left_chi_heavy", "left_chi_light",
                "right_cun_heavy", "right_cun_light",
                "right_guan_heavy", "right_guan_light",
                "right_chi_heavy", "right_chi_light"
            ).any { key -> json.has(key) && !json.isNull(key) }
        } catch (_: Exception) {
            false
        }
    }

    private fun selectedColorTemperatureK(): String = "auto"

    /** Silent device fingerprint for lighting calibration (never shown as a form). */
    private fun silentDeviceHint(): String {
        return listOf(
            "Android",
            Build.MANUFACTURER.orEmpty(),
            Build.MODEL.orEmpty(),
            Build.DEVICE.orEmpty(),
            "sdk=${Build.VERSION.SDK_INT}",
        ).joinToString("|")
    }

    private fun confoundersCsv(): String? {
        if (!binding.confounderFood.isChecked) return null
        return "近24小時飲食或藥物可能染色"
    }

    /** Immediate stool/urine analyze via same /api/record → MySQL as the website. */
    private fun submitCircleShot(kind: String, file: File) {
        try {
            rememberServer()
            runOnUiThread {
                Toast.makeText(this, t("toastCircleBusy"), Toast.LENGTH_SHORT).show()
            }
            val json = api.submit(
                symptoms = binding.symptoms.text.toString(),
                discomfort = binding.discomfort.text.toString(),
                face = faceFile,
                tongue = tongueFile,
                pulseJson = if (pulseReady(pulseJson)) pulseJson else null,
                colorTemperatureK = selectedColorTemperatureK(),
                shotType = kind,
                shotFile = file,
                confounders = confoundersCsv(),
                includePulse = pulseReady(pulseJson),
                deviceHint = silentDeviceHint(),
            )
            // Do not keep stool/urine photo for display.
            if (kind == CameraFacing.STOOL) stoolFile = null
            if (kind == CameraFacing.URINE) urineFile = null
            runOnUiThread {
                binding.result.text = prettyCircle(json, kind)
                bindAdvice(json)
                refreshTrend()
                refreshRecipeChoices(keepSelection = true)
                Toast.makeText(this, t("toastCircleSaved"), Toast.LENGTH_SHORT).show()
                binding.bodyImage.post {
                    Thread {
                        applyBodyOverlays(
                            binding.bodyMap,
                            binding.bodyImage,
                            json.optJSONObject("overlays"),
                            json.optJSONObject("scores"),
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

    private fun prettyCircle(json: JSONObject, kind: String): String {
        val label = if (kind == CameraFacing.URINE) "尿尿" else "大便"
        val findings = json.optJSONArray("findings")
        val lines = mutableListOf<String>()
        lines.add("${label}文字判斷（教學示範，非診斷）")
        if (findings != null) {
            for (i in 0 until findings.length()) {
                val text = findings.optString(i).trim()
                if (text.isNotBlank()) lines.add("・$text")
            }
        }
        val note = json.optJSONObject(kind)
        if (note != null) {
            val cls = note.optString("class_label").ifBlank { note.optString("label") }
            if (cls.isNotBlank()) lines.add("分類：$cls")
        }
        lines.add(pretty(json))
        return lines.joinToString("\n")
    }

    private fun save() {
        if (!pulseReady(pulseJson)) {
            runOnUiThread {
                Toast.makeText(
                    this,
                    "請先完成脈診。臉、舌與脈平均後，才確認臟腑實熱、實寒、虛熱、虛寒",
                    Toast.LENGTH_LONG
                ).show()
            }
            return
        }
        try {
            rememberServer()
            val json = api.submit(
                symptoms = binding.symptoms.text.toString(),
                discomfort = binding.discomfort.text.toString(),
                face = faceFile,
                tongue = tongueFile,
                pulseJson = pulseJson,
                colorTemperatureK = selectedColorTemperatureK(),
                deviceHint = silentDeviceHint(),
            )
            runOnUiThread {
                binding.result.text = pretty(json)
                bindAdvice(json)
                refreshTrend()
                refreshRecipeChoices(keepSelection = true)
                binding.bodyImage.post {
                    Thread {
                        applyBodyOverlays(
                            binding.bodyMap,
                            binding.bodyImage,
                            json.optJSONObject("overlays"),
                            json.optJSONObject("scores"),
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
                runOnUiThread { TrendCharts.bind(binding.trendChart, data.optJSONObject("trend"), female) }
            } catch (_: Exception) {
            }
        }.start()
    }

    private fun currentLang(): String {
        val stored = prefs.getString("ui_lang", "zh") ?: "zh"
        return if (stored in langCodes) stored else "zh"
    }

    private fun t(key: String): String = UiLang.t(currentLang(), key)

    private fun t(zh: String, en: String, ja: String, ko: String): String {
        return when (currentLang()) {
            "en" -> en
            "ja" -> ja
            "ko" -> ko
            else -> zh
        }
    }

    private fun applyLangChrome() {
        val lang = currentLang()
        binding.appSub.text = t("appSub")
        binding.langLabel.text = t("langLabel")
        binding.server.hint = t("serverHint")
        binding.password.hint = t("password")
        binding.captchaImage.contentDescription = t("captcha")
        binding.captchaRefresh.text = t("captchaRefresh")
        binding.captchaAnswer.hint = t("captcha")
        binding.login.text = t("login")
        binding.register.text = t("register")
        if (!binding.anon.text.toString().startsWith(t("anonPrefix")) &&
            binding.anon.text.toString().let { it == "尚未登入" || it == "Not signed in" || it == "未ログイン" || it == "로그인 안 됨" || it.isBlank() }
        ) {
            binding.anon.text = t("notLoggedIn")
        } else {
            val id = binding.anon.text.toString().substringAfter("：").substringAfter(": ").trim()
            if (id.isNotBlank() && id != t("notLoggedIn")) {
                binding.anon.text = t("anonPrefix") + id
            }
        }
        binding.profileHeading.text = t("profileHeading")
        binding.nickname.hint = t("nickname")
        binding.birthYear.hint = t("birthYear")
        binding.genderFemale.text = t("female")
        binding.genderMale.text = t("male")
        binding.genderOther.text = t("other")
        binding.height.hint = t("height")
        binding.weight.hint = t("weight")
        binding.conditionsHeading.text = t("conditions")
        binding.allergiesHeading.text = t("allergies")
        binding.saveProfile.text = t("saveProfile")
        binding.symptoms.hint = t("symptoms")
        binding.discomfort.hint = t("discomfort")
        binding.cct2700.text = t("cct2700")
        binding.cct4200.text = t("cct4200")
        binding.cct6500.text = t("cct6500")
        binding.shotFace.text = t("shotFace")
        binding.shotTongue.text = t("shotTongue")
        binding.shotStool.text = t("shotStool")
        binding.shotUrine.text = t("shotUrine")
        binding.circleNote.text = t("circleNote")
        binding.confounderFood.text = t("confounder")
        binding.openPulse.text = t("openPulse")
        binding.save.text = t("save")
        binding.trendHeading.text = t("trendHeading")
        binding.bodyHeading.text = t("bodyHeading")
        binding.recipeHeading.text = t("recipeHeading")
        binding.recipeNote.text = t("recipeNote")
        val advice = t("recipeBodyAdvice")
        binding.recipeBodyAdvice.textOn = advice
        binding.recipeBodyAdvice.textOff = advice
        binding.recipeCountry.hint = t("countryHint")
        binding.recipePick.hint = t("recipeHint")
        binding.recipeEnsure.text = t("recipeEnsure")
        // silence unused warning for lang in case of future locale config
        @Suppress("UNUSED_EXPRESSION")
        lang
    }

    private fun setupLanguageSpinner() {
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, langLabels)
        binding.langSelect.adapter = adapter
        val index = langCodes.indexOf(currentLang()).coerceAtLeast(0)
        binding.langSelect.setSelection(index)
        binding.langSelect.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                val code = langCodes.getOrNull(position) ?: "zh"
                if (code == currentLang()) {
                    applyLangChrome()
                    return
                }
                prefs.edit().putString("ui_lang", code).apply()
                applyLangChrome()
                Thread {
                    runCatching { api.updatePreferredLang(code) }
                }.start()
                val country = selectedCountry()
                if (country.isNotBlank()) requestRecipes(country, keepSelection = true)
                else refreshRecipeChoices(keepSelection = true)
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
    }

    private fun setupRecipeSpinners() {
        bindSearch(binding.recipeCountry, emptyList(), prefix = true)
        bindSearch(binding.recipePick, emptyList(), revealAll = true)
        binding.recipeCountry.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                val name = s?.toString()?.trim().orEmpty()
                if (name.isEmpty()) {
                    (binding.recipeCountry.adapter as? ArrayAdapter<*>)?.filter?.filter("")
                }
                if (name == loadedCountry && name.isNotEmpty()) return
                if (name in countryNames) {
                    requestRecipes(name)
                } else {
                    loadedCountry = ""
                    recipeLoadToken += 1
                    selectedRecipeId = -1
                    recipeRows = emptyList()
                    binding.recipePick.setText("", false)
                    bindSearch(binding.recipePick, emptyList(), revealAll = true)
                    binding.recipeDetail.text = ""
                }
            }
        })
        binding.recipePick.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                synchronized(this@MainActivity) { recipeShowAllPasses = 0 }
            }
            override fun afterTextChanged(s: Editable?) {
                val label = s?.toString()?.trim().orEmpty()
                if (label.isEmpty()) {
                    (binding.recipePick.adapter as? ArrayAdapter<*>)?.filter?.filter("")
                }
                showRecipeDetail(label)
            }
        })
        binding.recipeCountry.setOnFocusChangeListener { _, hasFocus ->
            if (hasFocus) showCountryMenu()
        }
        binding.recipeCountry.setOnClickListener { showCountryMenu() }
        binding.recipePick.setOnFocusChangeListener { _, hasFocus ->
            if (hasFocus) revealRecipeList()
        }
        binding.recipePick.setOnClickListener { revealRecipeList() }
        binding.recipeBodyAdvice.setOnCheckedChangeListener { _, _ ->
            refreshRecipeChoices(keepSelection = true)
        }
    }

    private fun showCountryMenu() {
        val adapter = binding.recipeCountry.adapter as? ArrayAdapter<*> ?: return
        val query = binding.recipeCountry.text?.toString()?.trim().orEmpty()
        if (query.isEmpty()) {
            adapter.filter.filter("") { binding.recipeCountry.showDropDown() }
        } else {
            binding.recipeCountry.showDropDown()
        }
    }

    private fun revealRecipeList() {
        if (selectedCountry().isBlank()) {
            showCountryMenu()
            return
        }
        if (recipeRows.isEmpty()) return
        synchronized(this) { recipeShowAllPasses = 2 }
        (binding.recipePick.adapter as? ArrayAdapter<*>)?.filter?.filter("") {
            binding.recipePick.showDropDown()
        }
    }

    private fun bindSearch(
        field: AutoCompleteTextView,
        items: List<String>,
        prefix: Boolean = false,
        revealAll: Boolean = false
    ) {
        val source = items.toList()
        val adapter = object : ArrayAdapter<String>(
            this,
            android.R.layout.simple_dropdown_item_1line,
            ArrayList(source)
        ) {
            private val searchFilter = object : Filter() {
                override fun performFiltering(constraint: CharSequence?): FilterResults {
                    val forceAll = if (revealAll) {
                        synchronized(this@MainActivity) {
                            if (recipeShowAllPasses > 0) {
                                recipeShowAllPasses -= 1
                                true
                            } else {
                                false
                            }
                        }
                    } else {
                        false
                    }
                    val query = if (forceAll) "" else constraint?.toString()?.trim().orEmpty()
                    val matched = when {
                        query.isEmpty() -> source
                        prefix -> source.filter { it.startsWith(query, ignoreCase = true) }
                        else -> source.filter { it.contains(query, ignoreCase = true) }
                    }
                    return FilterResults().apply {
                        values = ArrayList(matched)
                        count = matched.size
                    }
                }

                override fun publishResults(constraint: CharSequence?, results: FilterResults?) {
                    clear()
                    @Suppress("UNCHECKED_CAST")
                    addAll((results?.values as? List<String>) ?: emptyList())
                    if (count > 0) notifyDataSetChanged() else notifyDataSetInvalidated()
                }
            }

            override fun getFilter(): Filter = searchFilter
        }
        field.setAdapter(adapter)
        field.threshold = 1
    }

    private fun selectedCountry(): String {
        val name = binding.recipeCountry.text?.toString()?.trim().orEmpty()
        return if (name in countryNames) name else ""
    }

    private fun rememberJudgment(json: JSONObject) {
        val scores = JSONObject()
        val patterns = JSONObject()
        val nestedScores = json.optJSONObject("scores")
        val nestedPatterns = json.optJSONObject("patterns")
        organPatterns.forEach { (patternKey, _) ->
            val scoreKey = patternKey.removeSuffix("_pattern") + "_score"
            val scoreValue = when {
                nestedScores != null && nestedScores.has(scoreKey) -> nestedScores.opt(scoreKey)
                json.has(scoreKey) -> json.opt(scoreKey)
                else -> null
            }
            if (scoreValue != null && scoreValue != JSONObject.NULL && scoreValue.toString().isNotBlank()) {
                scores.put(scoreKey, scoreValue)
            }
            val patternValue = when {
                nestedPatterns != null && nestedPatterns.has(patternKey) -> nestedPatterns.optString(patternKey)
                json.has(patternKey) -> json.optString(patternKey)
                else -> ""
            }
            if (patternValue.isNotBlank()) patterns.put(patternKey, patternValue)
        }
        lastScoresJson = scores.toString()
        lastPatternsJson = patterns.toString()
        judgmentReady = scores.length() > 0 || patterns.length() > 0
    }

    private fun bindAdvice(json: JSONObject) {
        rememberJudgment(json)
        val diet = json.optString("diet_url")
        val dietVideo = json.optString("diet_video_url").ifBlank {
            googleVideoSearchFromWeb(diet)
        }
        val acu = json.optString("acupoint_url")
        val acuVideo = json.optString("acupoint_video_url").ifBlank {
            googleVideoSearchFromWeb(acu)
        }
        binding.dietLink.text = buildString {
            if (diet.isNotBlank()) {
                append(t("食譜文章搜尋", "Recipe articles", "レシピ記事検索", "레시피 글 검색"))
                append("\n")
                append(diet)
            }
            if (dietVideo.isNotBlank()) {
                if (isNotEmpty()) append("\n\n")
                append(t("食譜影片搜尋", "Recipe videos", "レシピ動画検索", "레시피 영상 검색"))
                append("\n")
                append(dietVideo)
            }
        }
        binding.acupointLink.text = buildString {
            if (acu.isNotBlank()) {
                append(t("穴道按摩圖片搜尋", "Acupoint massage images", "経穴マッサージ画像検索", "혈자리 마사지 이미지 검색"))
                append("\n")
                append(acu)
            }
            if (acuVideo.isNotBlank()) {
                if (isNotEmpty()) append("\n\n")
                append(t("穴道按摩影片搜尋", "Acupoint massage videos", "経穴マッサージ動画検索", "혈자리 마사지 영상 검색"))
                append("\n")
                append(acuVideo)
            }
        }
    }

    private fun googleVideoSearchFromWeb(url: String): String {
        if (url.isBlank()) return ""
        return try {
            val uri = android.net.Uri.parse(url)
            val q = uri.getQueryParameter("q") ?: return ""
            "https://www.google.com/search?tbm=vid&q=" + java.net.URLEncoder.encode(q, "UTF-8")
        } catch (_: Exception) {
            ""
        }
    }

    private fun loadLatestAdvice() {
        try {
            rememberServer()
            val data = api.records()
            val records = data.optJSONArray("records") ?: return
            if (records.length() == 0) return
            val latest = records.getJSONObject(0)
            runOnUiThread { bindAdvice(latest) }
        } catch (_: Exception) {
        }
    }

    private fun refreshRecipeChoices(keepSelection: Boolean = true) {
        val byBody = binding.recipeBodyAdvice.isChecked
        val country = binding.recipeCountry.text?.toString()?.trim().orEmpty()
        val keepId = if (keepSelection) selectedRecipeId else -1
        val scores = if (judgmentReady) lastScoresJson else ""
        val patterns = if (judgmentReady) lastPatternsJson else ""
        val lang = currentLang()
        val isFemale = female
        Thread {
            val names = fetchUsableCountries(byBody, scores, patterns, lang, isFemale, country) ?: return@Thread
            if (country.isNotBlank() && country in names) {
                val token = ++recipeLoadToken
                loadedCountry = country
                loadRecipes(country, token, keepId, byBody)
            }
        }.start()
    }

    private fun fetchUsableCountries(
        byBody: Boolean,
        scores: String,
        patterns: String,
        lang: String,
        isFemale: Boolean,
        currentCountry: String
    ): List<String>? {
        return try {
            rememberServer()
            val data = api.recipeCountries(lang, scores, patterns, isFemale, byBody)
            val arr = data.optJSONArray("countries") ?: JSONArray()
            val names = ArrayList<String>(arr.length())
            for (i in 0 until arr.length()) {
                val name = arr.optString(i).trim()
                if (name.isNotEmpty()) names.add(name)
            }
            countryNames = names
            runOnUiThread {
                bindSearch(binding.recipeCountry, names, prefix = true)
                if (currentCountry.isNotEmpty() && currentCountry !in names) {
                    loadedCountry = ""
                    selectedRecipeId = -1
                    recipeRows = emptyList()
                    binding.recipeCountry.setText("", false)
                    binding.recipePick.setText("", false)
                    bindSearch(binding.recipePick, emptyList(), revealAll = true)
                    binding.recipeDetail.text = ""
                }
            }
            names
        } catch (e: Exception) {
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
            null
        }
    }

    private fun ensureTypedRecipe() {
        val country = binding.recipeCountry.text?.toString()?.trim().orEmpty().ifBlank { "Global" }
        val name = binding.recipePick.text?.toString()?.trim().orEmpty()
        if (name.isBlank()) {
            runOnUiThread {
                Toast.makeText(this, "請先輸入要建立的食譜名稱", Toast.LENGTH_SHORT).show()
            }
            return
        }
        try {
            rememberServer()
            runOnUiThread { Toast.makeText(this, "建立食譜中…", Toast.LENGTH_SHORT).show() }
            val data = api.ensureRecipe(country, name, currentLang())
            runOnUiThread {
                val recipe = data.optJSONObject("recipe")
                val shown = recipe?.optString("name")?.ifBlank { name } ?: name
                Toast.makeText(
                    this,
                    if (data.optBoolean("created", true)) "已寫入共用食譜庫：$shown（網站／App 同步）"
                    else "已更新／取得：$shown",
                    Toast.LENGTH_LONG
                ).show()
                refreshRecipeChoices(keepSelection = false)
                if (recipe != null) showRecipeDetail(recipeLabel(recipe))
            }
        } catch (e: Exception) {
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    private fun requestRecipes(countryName: String, keepSelection: Boolean = false) {
        if (countryName.isBlank()) return
        val keepId = if (keepSelection) selectedRecipeId else -1
        if (!keepSelection) selectedRecipeId = -1
        val token = ++recipeLoadToken
        loadedCountry = countryName
        val byBody = binding.recipeBodyAdvice.isChecked
        Thread { loadRecipes(countryName, token, keepId, byBody) }.start()
    }

    private fun loadRecipes(countryName: String, token: Int, keepId: Int, byBody: Boolean) {
        if (countryName.isBlank()) return
        try {
            rememberServer()
            val scores = if (judgmentReady) lastScoresJson else ""
            val patterns = if (judgmentReady) lastPatternsJson else ""
            val data = api.recipes(countryName, currentLang(), scores, patterns, female, byBody)
            if (token != recipeLoadToken) return
            val arr = data.optJSONArray("recipes") ?: JSONArray()
            val rows = ArrayList<JSONObject>(arr.length())
            val labels = ArrayList<String>(arr.length())
            for (i in 0 until arr.length()) {
                val row = arr.optJSONObject(i) ?: continue
                rows.add(row)
                labels.add(recipeLabel(row))
            }
            recipeRows = rows
            runOnUiThread {
                if (token != recipeLoadToken) return@runOnUiThread
                bindSearch(binding.recipePick, labels, revealAll = true)
                val kept = if (keepId >= 0) rows.firstOrNull { it.optInt("id", -1) == keepId } else null
                if (kept != null) {
                    val label = recipeLabel(kept)
                    binding.recipePick.setText(label, false)
                    showRecipeDetail(label)
                } else {
                    selectedRecipeId = -1
                    binding.recipePick.setText("", false)
                    binding.recipeDetail.text = if (rows.isEmpty()) {
                        if (byBody) {
                            t(
                                "沒有符合今日檢測與過敏條件的食譜。教學示範，非診斷。",
                                "No recipes pass today’s reading and allergy filters. Teaching demo, not a diagnosis.",
                                "今日の検出とアレルギー条件に合うレシピがありません。教材であり診断ではありません。",
                                "오늘 검사와 알레르기 조건에 맞는 레시피가 없습니다. 교육용이며 진단이 아닙니다."
                            )
                        } else {
                            t(
                                "沒有符合過敏條件的食譜。教學示範，非診斷。",
                                "No recipes pass the allergy filter. Teaching demo, not a diagnosis.",
                                "アレルギー条件に合うレシピがありません。教材であり診断ではありません。",
                                "알레르기 조건에 맞는 레시피가 없습니다. 교육용이며 진단이 아닙니다."
                            )
                        }
                    } else ""
                }
            }
        } catch (e: Exception) {
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    private fun recipeLabel(row: JSONObject): String {
        val star = if (row.optBoolean("benefit_match")) " ★" else ""
        return row.optString("name") + star
    }

    private fun showRecipeDetail(label: String) {
        if (recipeRows.isEmpty()) return
        val row = recipeRows.firstOrNull { recipeLabel(it) == label }
        if (row == null) {
            selectedRecipeId = -1
            binding.recipeDetail.text = ""
            return
        }
        selectedRecipeId = row.optInt("id", -1)
        val recipe = t("食譜", "Recipe", "レシピ", "레시피")
        val method = t("煮法", "Method", "作り方", "조리법")
        val benefit = t("益處", "Benefits", "益処", "유익")
        val ban = t("禁忌", "Contraindications", "禁忌", "금기")
        val nutrient = t("元素", "Nutrients", "栄養素", "영양소")
        val allergens = t("過敏原", "Allergens", "アレルゲン", "알레르기 유발 물질")
        binding.recipeDetail.text = listOf(
            recipe to row.optString("recipe"),
            method to row.optString("method"),
            benefit to row.optString("benefit"),
            ban to row.optString("ban"),
            nutrient to row.optString("nutrient"),
            allergens to row.optString("allergens")
        ).filter { it.second.isNotBlank() }
            .joinToString("\n\n") { it.first + "\n" + it.second } +
            "\n\n" + t("教學示範，非診斷。", "Teaching demo, not a diagnosis.", "教材デモであり診断ではありません。", "교육 시연이며 진단이 아닙니다.")
    }

    private fun withoutMaleUterus(source: JSONObject?): JSONObject? {
        if (female || source == null) return source
        val copy = JSONObject()
        val keys = source.keys()
        while (keys.hasNext()) {
            val key = keys.next()
            if (key == "uterus" || key.startsWith("uterus_")) continue
            copy.put(key, source.get(key))
        }
        return copy
    }

    private fun healthyPatterns(scores: JSONObject?, patterns: JSONObject?): String {
        if (patterns == null) return ""
        val copy = JSONObject(patterns.toString())
        val keys = copy.keys()
        while (keys.hasNext()) {
            val patternKey = keys.next()
            if (!patternKey.endsWith("_pattern")) continue
            val scoreKey = patternKey.removeSuffix("_pattern") + "_score"
            val score = scores?.optInt(scoreKey, -1) ?: -1
            if (score >= 8) copy.put(patternKey, "健康")
        }
        return copy.toString()
    }

    private fun withoutMaleUterusText(text: String): String {
        if (female || !text.contains("子宮")) return text
        val kept = StringBuilder()
        val buf = StringBuilder()
        for (ch in text) {
            buf.append(ch)
            if (ch == '。' || ch == '；' || ch == '\n') {
                val sentence = buf.toString()
                if (!sentence.contains("子宮")) kept.append(sentence)
                buf.clear()
            }
        }
        if (buf.isNotEmpty() && !buf.contains("子宮")) kept.append(buf)
        return kept.toString().trim()
    }

    private fun pretty(json: JSONObject): String {
        val scores = json.optJSONObject("scores")
        val patterns = json.optJSONObject("patterns")
        rememberJudgment(json)
        val shownScores = withoutMaleUterus(scores)
        val shownPatterns = withoutMaleUterus(patterns)
        return "匿名紀錄已寫入 MySQL（教學參考，非診斷）\n" +
            "食療：" + withoutMaleUterusText(json.optString("diet_advice")) + "\n" +
            t("網路食療搜尋連結", "Diet search link", "食事療法の検索リンク", "식이요법 검색 링크") + "：" + json.optString("diet_url") + "\n" +
            t("穴道按摩圖片搜尋", "Acupoint massage images", "経穴マッサージ画像検索", "혈자리 마사지 이미지 검색") + "：" + json.optString("acupoint_url") + "\n" +
            t("穴道按摩影片搜尋", "Acupoint massage videos", "経穴マッサージ動画検索", "혈자리 마사지 영상 검색") + "：" +
            json.optString("acupoint_video_url").ifBlank { googleVideoSearchFromWeb(json.optString("acupoint_url")) } + "\n" +
            "分數：" + shownScores + "\n" +
            "證型：" + healthyPatterns(shownScores, shownPatterns)
    }
}
