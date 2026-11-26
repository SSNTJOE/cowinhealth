package com.tube.healthing

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.Editable
import android.text.TextWatcher
import android.text.method.LinkMovementMethod
import android.util.Base64
import android.util.Log
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.AutoCompleteTextView
import android.widget.Button
import android.widget.Filter
import android.widget.GridLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
// SearchLinks / BodyMap helpers used for labeled links + organ map UX
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.health.connect.client.PermissionController
import androidx.lifecycle.Lifecycle
import com.tube.healthing.databinding.ActivityMainBinding
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.LocalDate
import java.time.YearMonth
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private val api by lazy { ApiClient("", context = this) }
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

    companion object {
        private const val CAPTCHA_TAG = "HealthingCaptcha"
    }
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
    private var recipeEnsureToken = 0
    @Volatile private var recipeEnsureBusy = false
    private var recipeEnsureFollowUpName: String? = null
    private val recipeUiHandler = Handler(Looper.getMainLooper())
    private var recipeNameSearchRunnable: Runnable? = null
    private var recipeEnsureRunnable: Runnable? = null
    private var lastScoresJson = ""
    private var lastPatternsJson = ""
    private var judgmentReady = false
    private var selectedRecipeId = -1
    @Volatile private var recipeShowAllPasses = 0
    private var cameraProvider: ProcessCameraProvider? = null
    private var startingCamera = false
    private var cameraBindGeneration = 0
    private var flagAllergyOptions: List<String> = emptyList()
    private val stepsReader by lazy { StepsReader(this, prefs) }
    private var pendingStepsAction: String? = null
    private val mealSlotValues = listOf("早餐", "午餐", "晚餐", "點心")
    private var mealSelectedDate: LocalDate = LocalDate.now()
    private var mealViewYear: Int = LocalDate.now().year
    private var mealViewMonth: Int = LocalDate.now().monthValue
    private var mealMonthData: JSONObject? = null
    private var mealDayData: JSONObject? = null
    private var mealLoadToken = 0

    private val permission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> if (granted) startCamera() }

    private val activityRecognitionPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            when (pendingStepsAction) {
                "sync" -> Thread { syncStepsFromDevice() }.start()
                else -> {}
            }
        } else {
            Toast.makeText(this, t("stepsNote"), Toast.LENGTH_LONG).show()
        }
        pendingStepsAction = null
    }

    private val healthConnectPermission = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        if (granted.containsAll(stepsReader.healthConnectPermissions())) {
            Thread { syncStepsFromDevice(preferHc = true) }.start()
        } else {
            Thread { syncStepsFromDevice(preferHc = false) }.start()
        }
    }

    private val pulseLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            pulseJson = result.data?.getStringExtra("pulse_json")
            val summary = result.data?.getStringExtra("organ_summary").orEmpty().ifBlank {
                try {
                    org.json.JSONObject(pulseJson ?: "{}").optString("organ_summary")
                } catch (_: Exception) {
                    ""
                }
            }
            binding.result.text = if (summary.isNotBlank()) {
                "脈診完成（教學參考，非診斷）\n$summary"
            } else {
                "脈診完成（已回傳寸關尺讀數）"
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        HealthFlags.inflate(binding.conditionsGroup, HealthFlags.CONDITIONS)
        HealthFlags.inflate(binding.allergiesGroup, HealthFlags.ALLERGIES, columns = 3)
        CameraFacing.ensureDefaults(this)
        binding.preview.implementationMode = PreviewView.ImplementationMode.COMPATIBLE
        binding.preview.scaleType = PreviewView.ScaleType.FILL_CENTER
        ensureLoginFieldsEditable()
        val savedUrl = sanitizeBaseUrl(prefs.getString("base_url", getString(R.string.default_base_url)))
        binding.server.setText(savedUrl)
        if (savedUrl.isNotBlank()) {
            api.setBaseUrl(savedUrl)
        }
        binding.result.movementMethod = LinkMovementMethod.getInstance()
        binding.dietLink.movementMethod = LinkMovementMethod.getInstance()
        binding.acupointLink.movementMethod = LinkMovementMethod.getInstance()
        setupLanguageSpinner()
        setupRecipeSpinners()
        applyLangChrome()
        refreshSyndromeLegend()
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

        binding.serverApply.setOnClickListener {
            if (!rememberServer(showFeedback = true)) return@setOnClickListener
            Toast.makeText(this, t("toastServerSaved"), Toast.LENGTH_SHORT).show()
            Thread { refreshCaptcha() }.start()
        }
        binding.captchaRefresh.setOnClickListener { Thread { refreshCaptcha() }.start() }
        if (savedUrl.isNotBlank() && !looksLikePlaceholderHost(savedUrl)) {
            Thread { refreshCaptcha() }.start()
        }
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
        binding.stepsRefresh.setOnClickListener { requestSyncSteps() }
        binding.stepsSaveManual.setOnClickListener { Thread { saveManualSteps() }.start() }
        binding.recipeEnsure.setOnClickListener { Thread { ensureTypedRecipe() }.start() }
        setupMealCalendar()
        binding.genderGroup.setOnCheckedChangeListener { _, checkedId ->
            female = checkedId == binding.genderFemale.id
            loadBodyImage()
        }
        // Show bundled 臟腑圖 immediately (server media is optional overlay source).
        loadBodyImage()

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
        cameraBindGeneration += 1
        startingCamera = false
        cameraProvider?.unbindAll()
        imageCapture = null
        super.onPause()
    }

    private fun ensureLoginFieldsEditable() {
        listOf(
            binding.server,
            binding.email,
            binding.password,
            binding.captchaAnswer,
        ).forEach { field ->
            field.isEnabled = true
            field.isFocusable = true
            field.isFocusableInTouchMode = true
            field.isClickable = true
        }
    }

    /** True for docs placeholders like 192.168.x.x / x.x / 電腦區網IP. */
    private fun looksLikePlaceholderHost(raw: String): Boolean {
        val url = raw.trim()
        if (url.isBlank()) return false
        val host = extractHost(url) ?: return true
        val lower = host.lowercase()
        if (lower.contains("x.x") || lower.contains("lan-ip") || lower.contains("your-") ||
            lower.contains("example") || host.contains("電腦") || host.contains("區網")
        ) {
            return true
        }
        val parts = host.split('.')
        if (parts.any { p ->
                val t = p.trim()
                t.equals("x", true) || t == "*" || t.equals("xx", true) ||
                    t.equals("yyy", true) || t.equals("nnn", true)
            }
        ) {
            return true
        }
        return false
    }

    private fun extractHost(raw: String): String? {
        val trimmed = raw.trim()
        if (trimmed.isBlank()) return null
        val withScheme = if ("://" in trimmed) trimmed else "http://$trimmed"
        return try {
            val uri = android.net.Uri.parse(withScheme)
            uri.host?.takeIf { it.isNotBlank() }
        } catch (_: Exception) {
            null
        }
    }

    private fun sanitizeBaseUrl(raw: String?): String {
        val url = raw?.trim()?.trimEnd('/') ?: ""
        if (url.isBlank()) return ""
        if (looksLikePlaceholderHost(url)) {
            prefs.edit().remove("base_url").apply()
            return ""
        }
        return url
    }

    private fun normalizeServerUrl(raw: String): String {
        var url = raw.trim().trimEnd('/')
        if (url.isBlank()) return ""
        if (!url.contains("://")) url = "http://$url"
        return url.trimEnd('/')
    }

    private fun rememberServer(showFeedback: Boolean = false): Boolean {
        val url = normalizeServerUrl(binding.server.text.toString())
        if (url.isBlank()) {
            if (showFeedback) {
                runOnUiThread {
                    Toast.makeText(this, t("toastServerEmpty"), Toast.LENGTH_LONG).show()
                }
            }
            return false
        }
        if (looksLikePlaceholderHost(url)) {
            runOnUiThread {
                Toast.makeText(this, t("toastServerPlaceholder"), Toast.LENGTH_LONG).show()
            }
            return false
        }
        if (extractHost(url) == null) {
            runOnUiThread {
                Toast.makeText(this, t("toastServerEmpty"), Toast.LENGTH_LONG).show()
            }
            return false
        }
        runOnUiThread {
            if (binding.server.text.toString().trim().trimEnd('/') != url) {
                binding.server.setText(url)
            }
        }
        prefs.edit().putString("base_url", url).apply()
        api.setBaseUrl(url)
        return true
    }

    private fun friendlyNetworkError(e: Exception): String {
        val msg = (e.message ?: "")
        val lower = msg.lowercase()
        val cause = (e.cause?.message ?: "").lowercase()
        val blob = "$lower $cause ${e.javaClass.simpleName.lowercase()}"
        if (looksLikePlaceholderHost(binding.server.text.toString()) || blob.contains("192.168.x.x")) {
            return t("toastServerPlaceholder")
        }
        if (blob.contains("captcha_dns") || blob.contains("unable to resolve host") ||
            blob.contains("unknownhost") || blob.contains("no address associated")
        ) {
            return t("toastCaptchaDns")
        }
        if (blob.contains("captcha_refused") || blob.contains("connection refused") ||
            blob.contains("econnrefused") || blob.contains("connectexception")
        ) {
            return t("toastCaptchaRefused")
        }
        if (blob.contains("captcha_timeout") || blob.contains("timed out") || blob.contains("timeout") ||
            blob.contains("network is unreachable") || blob.contains("failed to connect")
        ) {
            return t("toastCaptchaTimeout")
        }
        if (blob.contains("captcha_cleartext") || blob.contains("cleartext") || blob.contains("plaintext http")) {
            return t("toastCaptchaCleartext")
        }
        if (blob.contains("captcha_decode") || blob.contains("captcha_bad_json") ||
            blob.contains("decode") && blob.contains("captcha")
        ) {
            return t("toastCaptchaDecode")
        }
        if (blob.contains("unable to resolve") || blob.contains("failed to connect") ||
            blob.contains("connectexception")
        ) {
            return t("toastServerUnreachable")
        }
        return msg.takeIf { it.isNotBlank() && !it.startsWith("CAPTCHA_") } ?: t("toastCaptchaFail")
    }

    /** Strip data-URL prefix / whitespace; tolerate URL-safe and NO_WRAP base64. */
    private fun decodeCaptchaBase64(raw: String): Bitmap? {
        var b64 = raw.trim()
        if (b64.isEmpty()) return null
        val comma = b64.indexOf(',')
        if (b64.startsWith("data:", ignoreCase = true) && comma >= 0) {
            b64 = b64.substring(comma + 1).trim()
        }
        // Web may send data URI; API returns raw base64 — strip whitespace/newlines either way.
        b64 = b64.replace("\\s".toRegex(), "")
        val flags = intArrayOf(Base64.DEFAULT, Base64.NO_WRAP, Base64.URL_SAFE or Base64.NO_WRAP)
        var bytes: ByteArray? = null
        for (flag in flags) {
            try {
                bytes = Base64.decode(b64, flag)
                if (bytes != null && bytes.isNotEmpty()) break
            } catch (_: IllegalArgumentException) {
                bytes = null
            }
        }
        if (bytes == null || bytes.isEmpty()) {
            Log.w(CAPTCHA_TAG, "base64 decode failed len=${b64.length} head=${b64.take(24)}")
            return null
        }
        // PNG magic — reject HTML/JSON accident payloads early.
        if (bytes.size >= 8 &&
            !(bytes[0] == 0x89.toByte() && bytes[1] == 0x50.toByte() && bytes[2] == 0x4E.toByte())
        ) {
            Log.w(CAPTCHA_TAG, "decoded bytes not PNG magic size=${bytes.size} b0=${bytes[0].toInt() and 0xff}")
        }
        val opts = BitmapFactory.Options().apply { inPreferredConfig = Bitmap.Config.ARGB_8888 }
        val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts)
        if (bmp == null) {
            Log.w(CAPTCHA_TAG, "BitmapFactory returned null size=${bytes.size}")
        } else {
            Log.i(CAPTCHA_TAG, "decoded bitmap ${bmp.width}x${bmp.height} from ${bytes.size} bytes")
        }
        return bmp
    }

    private fun captchaErrorBitmap(message: String): Bitmap {
        val w = 400
        val h = 128
        val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bmp)
        canvas.drawColor(Color.parseColor("#FFEBEE"))
        val border = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#C62828")
            style = Paint.Style.STROKE
            strokeWidth = 3f
        }
        canvas.drawRect(1.5f, 1.5f, w - 1.5f, h - 1.5f, border)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#B71C1C")
            textSize = 28f
            typeface = Typeface.DEFAULT_BOLD
            textAlign = Paint.Align.CENTER
        }
        val maxWidth = w - 24f
        val words = message.split(' ', '，', '。', '；', '\n')
        val lines = mutableListOf<String>()
        var line = ""
        for (word in words) {
            if (word.isBlank()) continue
            val candidate = if (line.isEmpty()) word else "$line $word"
            if (paint.measureText(candidate) <= maxWidth) {
                line = candidate
            } else {
                if (line.isNotEmpty()) lines.add(line)
                line = word
            }
        }
        if (line.isNotEmpty()) lines.add(line)
        if (lines.isEmpty()) lines.add(message.take(24))
        val shown = lines.take(3)
        var y = (h - shown.size * 34f) / 2f + 28f
        for (row in shown) {
            canvas.drawText(row, w / 2f, y, paint)
            y += 34f
        }
        return bmp
    }

    private fun showCaptchaFailure(message: String) {
        captchaToken = ""
        binding.captchaImage.clearColorFilter()
        binding.captchaImage.imageTintList = null
        binding.captchaImage.scaleType = ImageView.ScaleType.FIT_CENTER
        binding.captchaImage.setImageBitmap(captchaErrorBitmap(message))
        binding.captchaImage.contentDescription = message
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    private fun refreshCaptcha() {
        try {
            if (!rememberServer(showFeedback = true)) {
                runOnUiThread {
                    val msg = when {
                        binding.server.text.toString().isBlank() -> t("toastServerEmpty")
                        looksLikePlaceholderHost(binding.server.text.toString()) -> t("toastServerPlaceholder")
                        else -> t("toastCaptchaFail")
                    }
                    showCaptchaFailure(msg)
                }
                return
            }
            Log.i(CAPTCHA_TAG, "refresh baseUrl=${binding.server.text}")
            val json = api.captcha()
            val token = json.optString("captcha_token")
            // Prefer image_base64 (API); accept aliases if a proxy rewrites JSON.
            var b64 = json.optString("image_base64")
            if (b64.isBlank()) b64 = json.optString("imageBase64")
            if (b64.isBlank()) b64 = json.optString("image")
            if (token.isBlank() || b64.isBlank()) {
                throw RuntimeException("CAPTCHA_BAD_JSON: token blank=${token.isBlank()} b64 blank=${b64.isBlank()}")
            }
            val bmp = decodeCaptchaBase64(b64)
                ?: throw RuntimeException("CAPTCHA_DECODE: BitmapFactory failed")
            if (bmp.width < 8 || bmp.height < 8) {
                throw RuntimeException("CAPTCHA_DECODE: bitmap too small ${bmp.width}x${bmp.height}")
            }
            captchaToken = token
            runOnUiThread {
                binding.captchaImage.clearColorFilter()
                binding.captchaImage.imageTintList = null
                binding.captchaImage.setColorFilter(null)
                binding.captchaImage.scaleType = ImageView.ScaleType.FIT_CENTER
                binding.captchaImage.setImageBitmap(bmp)
                binding.captchaImage.contentDescription = t("captcha")
                binding.captchaAnswer.setText("")
            }
            Log.i(CAPTCHA_TAG, "captcha ImageView updated ${bmp.width}x${bmp.height}")
        } catch (e: Exception) {
            Log.e(CAPTCHA_TAG, "refreshCaptcha failed: ${e.javaClass.simpleName} ${e.message}", e)
            val msg = friendlyNetworkError(e)
            runOnUiThread { showCaptchaFailure(msg) }
        }
    }

    private fun loadFlagOptions() {
        try {
            if (!rememberServer()) return
            val flags = api.flags()
            runOnUiThread { applyFlagOptions(flags) }
        } catch (_: Exception) {
        }
    }

    private fun login() {
        try {
            if (!rememberServer(showFeedback = true)) return
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
            refreshStepsSummaryOnly()
            refreshMealCalendar()
            refreshCaptcha()
        } catch (e: Exception) {
            refreshCaptcha()
            runOnUiThread { Toast.makeText(this, friendlyNetworkError(e), Toast.LENGTH_LONG).show() }
        }
    }

    private fun register() {
        try {
            if (!rememberServer(showFeedback = true)) return
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
            refreshStepsSummaryOnly()
            refreshMealCalendar()
            refreshCaptcha()
        } catch (e: Exception) {
            refreshCaptcha()
            runOnUiThread { Toast.makeText(this, friendlyNetworkError(e), Toast.LENGTH_LONG).show() }
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
            HealthFlags.inflate(binding.allergiesGroup, options, columns = 3)
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
            HealthFlags.inflate(binding.allergiesGroup, allergyOptions, columns = 3)
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

    private fun startCamera(retry: Int = 0) {
        // TextureView works inside ScrollView; SurfaceView (PERFORMANCE) stays black.
        if (!lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) return
        binding.preview.implementationMode = PreviewView.ImplementationMode.COMPATIBLE
        binding.preview.scaleType = PreviewView.ScaleType.FILL_CENTER
        if (!binding.preview.isAttachedToWindow) return
        if (binding.preview.width == 0 || binding.preview.height == 0) {
            binding.preview.post { startCamera(retry) }
            return
        }
        if (startingCamera && retry == 0) return
        startingCamera = true
        val generation = ++cameraBindGeneration
        val wantKind = alignKind
        val providerFuture = ProcessCameraProvider.getInstance(this)
        providerFuture.addListener({
            if (generation != cameraBindGeneration) {
                startingCamera = false
                return@addListener
            }
            if (!lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) {
                startingCamera = false
                return@addListener
            }
            if (!binding.preview.isAttachedToWindow) {
                startingCamera = false
                return@addListener
            }
            if (binding.preview.width == 0 || binding.preview.height == 0) {
                startingCamera = false
                binding.preview.post { startCamera(retry) }
                return@addListener
            }
            try {
                val provider = providerFuture.get()
                cameraProvider = provider
                // Pulse uses front camera + screen green fill (no rear torch).
                try {
                    provider.unbindAll()
                } catch (_: Exception) {
                }
                var capture: ImageCapture? = null
                var bound = false
                val attempts = buildList {
                    add(null as android.util.Size?)
                    addAll(CameraBind.trySizes())
                }
                for (size in attempts) {
                    if (generation != cameraBindGeneration || alignKind != wantKind) break
                    val previewBuilder = Preview.Builder()
                    val captureBuilder = ImageCapture.Builder()
                    if (size != null) {
                        val selector = CameraBind.resolution(size)
                        previewBuilder.setResolutionSelector(selector)
                        captureBuilder.setResolutionSelector(selector)
                    }
                    val preview = previewBuilder.build()
                    // Set surface before bind — more reliable for first front-camera open on OEMs.
                    preview.setSurfaceProvider(binding.preview.surfaceProvider)
                    capture = captureBuilder.build()
                    if (CameraBind.bindForCaptureKind(
                            this, provider, this, wantKind, preview, capture
                        ) != null
                    ) {
                        applyAlignGuides(wantKind)
                        bound = true
                        break
                    }
                }
                if (generation != cameraBindGeneration) {
                    startingCamera = false
                    return@addListener
                }
                imageCapture = if (bound) capture else null
                if (!bound) {
                    val wantFront = CameraFacing.isFront(this, wantKind)
                    // Front lens often needs a short HAL warm-up on first open after cold start.
                    if (wantFront && retry < 4) {
                        startingCamera = false
                        binding.preview.postDelayed({
                            if (lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED) &&
                                alignKind == wantKind
                            ) {
                                startCamera(retry + 1)
                            }
                        }, 180L * (retry + 1))
                        return@addListener
                    }
                    val lens = if (wantFront) "前置" else "後置"
                    Toast.makeText(
                        this,
                        "打不開${lens}鏡頭（${wantKind}）。模擬器請檢查 Front/Back camera 設定。",
                        Toast.LENGTH_LONG
                    ).show()
                }
            } catch (e: Exception) {
                imageCapture = null
                if (CameraFacing.isFront(this, wantKind) && retry < 4) {
                    startingCamera = false
                    binding.preview.postDelayed({
                        if (lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) {
                            startCamera(retry + 1)
                        }
                    }, 180L * (retry + 1))
                    return@addListener
                }
                Toast.makeText(this, e.message ?: "無法開啟鏡頭", Toast.LENGTH_LONG).show()
            } finally {
                if (generation == cameraBindGeneration) {
                    startingCamera = false
                }
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun showAlign(kind: String) {
        val previousKind = alignKind
        val previousFacing = CameraFacing.facingString(this, previousKind)
        alignKind = CameraFacing.normalize(kind)
        applyAlignGuides(alignKind)
        val facingChanged = previousFacing != CameraFacing.facingString(this, alignKind)
        val kindChanged = previousKind != alignKind
        // Always rebind when mode or lens changes, and when preview was never bound
        // (first face/tongue after launch must open front without a prior rear bind).
        if (facingChanged || kindChanged || imageCapture == null) {
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
        // Face / tongue / circle use digital preview zoom around center.
        val zoom = when {
            face -> FaceFrame.PREVIEW_ZOOM
            tongue -> TongueFrame.PREVIEW_ZOOM
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
                CameraFacing.FACE -> "臉部黃框已變窄、預覽放大兩倍，對準黃線後再按一次"
                CameraFacing.TONGUE -> "舌頭預覽已放大兩倍，對準黃框後再按一次"
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
            startCamera()
            val lens = if (CameraFacing.isFront(this, mode)) "前置" else "後置"
            Toast.makeText(this, "鏡頭啟動中（$mode 用${lens}鏡頭），請稍候再按一次", Toast.LENGTH_SHORT).show()
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
            refreshMealCalendar()
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
                bindOrganSessionUi(json)
                refreshTrend()
                refreshRecipeChoices(keepSelection = true)
                Toast.makeText(
                    this,
                    StoolUrineJudge.toastLine(json, kind),
                    Toast.LENGTH_LONG,
                ).show()
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

    /** Brief stool/urine conclusions (same idea as pulse 五臟六腑簡結). */
    private fun prettyCircle(json: JSONObject, kind: String): String {
        val summary = StoolUrineJudge.summaryFromResult(json, kind)
        // Keep diet/score footer short; detailed findings stay in session summary / organ cards.
        return "$summary\n\n${pretty(json)}"
    }

    private fun save() {
        // Face / tongue / stool / urine / 寸關尺 are all optional.
        // Server averages organ scores from measured modalities only.
        try {
            rememberServer()
            val hasPulse = pulseReady(pulseJson)
            val json = api.submit(
                symptoms = binding.symptoms.text.toString(),
                discomfort = binding.discomfort.text.toString(),
                face = faceFile,
                tongue = tongueFile,
                pulseJson = if (hasPulse) pulseJson else null,
                colorTemperatureK = selectedColorTemperatureK(),
                includePulse = hasPulse,
                deviceHint = silentDeviceHint(),
            )
            runOnUiThread {
                binding.result.text = pretty(json)
                bindAdvice(json)
                bindOrganSessionUi(json)
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
        female = binding.genderFemale.isChecked ||
            (!binding.genderMale.isChecked && !binding.genderOther.isChecked && female)
        val name = if (female) "girl-body.png" else "boy-body.png"
        Thread {
            val bmp = decodeMediaBitmap(this, name, api::mediaUrl, http) ?: return@Thread
            runOnUiThread {
                binding.bodyImage.setImageBitmap(bmp)
                binding.bodyImage.contentDescription =
                    if (female) t("bodyAltGirl") else t("bodyAltBoy")
            }
        }.start()
    }

    private fun refreshTrend() {
        Thread {
            try {
                val data = api.records()
                runOnUiThread {
                    TrendCharts.bind(
                        binding.trendChart,
                        data.optJSONObject("trend"),
                        female,
                        binding.trendEmpty,
                        t("trendEmpty"),
                    )
                }
            } catch (_: Exception) {
                runOnUiThread {
                    TrendCharts.bind(
                        binding.trendChart,
                        null,
                        female,
                        binding.trendEmpty,
                        t("trendEmpty"),
                    )
                }
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
        binding.serverNote.text = t("serverNote")
        binding.serverApply.text = t("serverApply")
        binding.password.hint = t("password")
        binding.captchaNote.text = t("captchaNote")
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
        binding.bodyHeading.text = t("bodyHeading")
        binding.bodyNote.text = t("bodyNote")
        binding.organScoresHeading.text = t("organScoresHeading")
        binding.sessionSummaryHeading.text = t("sessionSummaryHeading")
        if (binding.sessionSummary.text.isNullOrBlank() ||
            binding.sessionSummary.text.toString() in setOf(
                "送出紀錄後會顯示今日總結（教學示範，非診斷）。",
                "Submit today’s record to see the session summary (teaching demo, not diagnosis).",
                "記録を送ると本日のまとめが表示されます（教材デモ、診断ではありません）。",
                "기록을 보내면 오늘 요약이 표시됩니다(교육 시연, 진단 아님).",
            )
        ) {
            binding.sessionSummary.text = t("sessionSummaryIdle")
        }
        binding.trendHeading.text = t("trendHeading")
        binding.trendNote.text = t("trendNote")
        binding.trendEmpty.text = t("trendEmpty")
        refreshSyndromeLegend()
        binding.recipeHeading.text = t("recipeHeading")
        binding.recipeNote.text = t("recipeNote")
        val advice = t("recipeBodyAdvice")
        binding.recipeBodyAdvice.textOn = advice
        binding.recipeBodyAdvice.textOff = advice
        binding.recipeCountry.hint = t("countryHint")
        binding.recipePick.hint = t("recipeHint")
        binding.recipeEnsure.text = t("recipeEnsure")
        binding.stepsHeading.text = t("stepsHeading")
        binding.stepsNote.text = t("stepsNote")
        if (binding.stepsSummary.text.isNullOrBlank() ||
            binding.stepsSummary.text.toString() in setOf(
                "登入後可讀取／同步今日步數",
                "Sign in to read/sync today’s steps",
                "ログイン後に本日の歩数を読取／同期できます",
                "로그인 후 오늘 걸음을 읽기/동기화할 수 있습니다",
                "로그인 후 오늘 걸음 수를 읽기/동기화할 수 있습니다",
            )
        ) {
            binding.stepsSummary.text = t("stepsSummaryIdle")
        }
        binding.stepsManual.hint = t("stepsManualHint")
        binding.stepsRefresh.text = t("stepsRefresh")
        binding.stepsSaveManual.text = t("stepsSaveManual")
        binding.mealCalendarHeading.text = t("mealCalendarHeading")
        binding.mealCalendarNote.text = t("mealCalendarNote")
        binding.mealAdd.text = t("mealAdd")
        binding.mealServings.hint = t("mealServingsHint")
        binding.mealNutrientHeading.text = t("mealNutrientHeading")
        binding.mealTrendHeading.text = t("mealTrendHeading")
        applyMealSlotLabels()
        if (apiTokenMissing()) {
            binding.mealNutrientEmpty.text = t("mealIdle")
            binding.mealNutrientEmpty.visibility = View.VISIBLE
            clearMealCharts()
        }
        // silence unused warning for lang in case of future locale config
        @Suppress("UNUSED_EXPRESSION")
        lang
    }


    private fun setupMealCalendar() {
        applyMealSlotLabels()
        binding.mealMonthPrev.setOnClickListener {
            var m = mealViewMonth - 1
            var y = mealViewYear
            if (m < 1) {
                m = 12
                y -= 1
            }
            mealViewYear = y
            mealViewMonth = m
            Thread { loadMealMonthOnly() }.start()
        }
        binding.mealMonthNext.setOnClickListener {
            var m = mealViewMonth + 1
            var y = mealViewYear
            if (m > 12) {
                m = 1
                y += 1
            }
            mealViewYear = y
            mealViewMonth = m
            Thread { loadMealMonthOnly() }.start()
        }
        binding.mealAdd.setOnClickListener { Thread { addSelectedMeal() }.start() }
        showMealIdleState()
    }

    private fun applyMealSlotLabels() {
        val labels = listOf(
            t("mealBreakfast"),
            t("mealLunch"),
            t("mealDinner"),
            t("mealSnack"),
        )
        val selected = binding.mealSlot.selectedItemPosition.coerceIn(0, mealSlotValues.lastIndex)
        binding.mealSlot.adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_dropdown_item,
            labels,
        )
        binding.mealSlot.setSelection(selected)
    }

    private fun showMealIdleState() {
        binding.mealMonthLabel.text = "%04d-%02d".format(mealViewYear, mealViewMonth)
        binding.mealDayMeta.text = ""
        binding.mealList.removeAllViews()
        binding.mealNutrientEmpty.text = t("mealIdle")
        binding.mealNutrientEmpty.visibility = View.VISIBLE
        clearMealCharts()
        binding.mealCalendarGrid.removeAllViews()
    }

    private fun clearMealCharts() {
        val empty = t("mealIdle")
        MealNutrientCharts.bindIntakeBar(
            binding.mealIntakeChart,
            null,
            empty,
            t("mealIntakeSeries"),
            t("mealTargetSeries"),
        )
        MealNutrientCharts.bindSurplusTrend(
            binding.mealTrendChart,
            null,
            null,
            empty,
        )
    }

    private fun bindMealCharts(day: JSONObject?, month: JSONObject?, emptyHint: String) {
        MealNutrientCharts.bindIntakeBar(
            binding.mealIntakeChart,
            day,
            emptyHint,
            t("mealIntakeSeries"),
            t("mealTargetSeries"),
        )
        MealNutrientCharts.bindSurplusTrend(
            binding.mealTrendChart,
            month,
            day,
            emptyHint,
        )
    }

    private fun refreshMealCalendar() {
        if (apiTokenMissing()) {
            runOnUiThread { showMealIdleState() }
            return
        }
        val token = ++mealLoadToken
        try {
            rememberServer()
            val month = api.mealsMonth(mealViewYear, mealViewMonth)
            val day = api.mealsDay(mealSelectedDate.toString())
            if (token != mealLoadToken) return
            mealMonthData = month
            mealDayData = day
            runOnUiThread {
                if (token != mealLoadToken) return@runOnUiThread
                renderMealCalendarGrid()
                renderMealDay()
            }
        } catch (e: Exception) {
            if (token != mealLoadToken) return
            runOnUiThread {
                binding.mealNutrientEmpty.text = e.message ?: t("mealIdle")
                binding.mealNutrientEmpty.visibility = View.VISIBLE
            }
        }
    }

    private fun loadMealMonthOnly() {
        if (apiTokenMissing()) {
            runOnUiThread { showMealIdleState() }
            return
        }
        val token = ++mealLoadToken
        try {
            rememberServer()
            val month = api.mealsMonth(mealViewYear, mealViewMonth)
            if (token != mealLoadToken) return
            mealMonthData = month
            runOnUiThread {
                if (token != mealLoadToken) return@runOnUiThread
                renderMealCalendarGrid()
                bindMealCharts(mealDayData, mealMonthData, t("mealChartEmpty"))
            }
        } catch (e: Exception) {
            if (token != mealLoadToken) return
            runOnUiThread {
                Toast.makeText(this, e.message, Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun loadMealDayOnly() {
        if (apiTokenMissing()) return
        val token = ++mealLoadToken
        try {
            rememberServer()
            val day = api.mealsDay(mealSelectedDate.toString())
            if (token != mealLoadToken) return
            mealDayData = day
            runOnUiThread {
                if (token != mealLoadToken) return@runOnUiThread
                renderMealCalendarGrid()
                renderMealDay()
            }
        } catch (e: Exception) {
            if (token != mealLoadToken) return
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    private fun renderMealCalendarGrid() {
        val grid = binding.mealCalendarGrid
        grid.removeAllViews()
        binding.mealMonthLabel.text = "%04d-%02d".format(mealViewYear, mealViewMonth)
        val dowLabels = when (currentLang()) {
            "en" -> listOf("M", "T", "W", "T", "F", "S", "S")
            "ja" -> listOf("月", "火", "水", "木", "金", "土", "日")
            "ko" -> listOf("월", "화", "수", "목", "금", "토", "일")
            else -> listOf("一", "二", "三", "四", "五", "六", "日")
        }
        val cellW = (resources.displayMetrics.widthPixels -
            TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, 48f, resources.displayMetrics).toInt()) / 7
        fun addCell(view: View) {
            val lp = GridLayout.LayoutParams().apply {
                width = cellW
                height = ViewGroup.LayoutParams.WRAP_CONTENT
                setMargins(2, 2, 2, 2)
            }
            grid.addView(view, lp)
        }
        for (name in dowLabels) {
            addCell(TextView(this).apply {
                text = name
                gravity = Gravity.CENTER
                setTypeface(typeface, Typeface.BOLD)
                textSize = 12f
            })
        }
        val ym = YearMonth.of(mealViewYear, mealViewMonth)
        val first = ym.atDay(1)
        val startPad = (first.dayOfWeek.value + 6) % 7 // Monday-first
        for (i in 0 until startPad) {
            addCell(TextView(this).apply { text = "" })
        }
        val byDate = mutableMapOf<String, JSONObject>()
        val days = mealMonthData?.optJSONArray("days")
        if (days != null) {
            for (i in 0 until days.length()) {
                val d = days.optJSONObject(i) ?: continue
                byDate[d.optString("date")] = d
            }
        }
        val today = LocalDate.now().toString()
        for (dayNum in 1..ym.lengthOfMonth()) {
            val iso = "%04d-%02d-%02d".format(mealViewYear, mealViewMonth, dayNum)
            val info = byDate[iso]
            val hasMeals = info?.optBoolean("has_meals") == true
            val btn = TextView(this).apply {
                val pct = if (info == null || info.isNull("kcal_pct")) null
                else info.optDouble("kcal_pct")
                val meta = if (hasMeals) {
                    val count = t("mealCountLabel").replace("{n}", info?.optInt("meal_count", 0).toString())
                    val pctText = pct?.let {
                        val n = if (it == it.toInt().toDouble()) it.toInt().toString() else it.toString()
                        "\n" + t("mealKcalPct").replace("{n}", n)
                    }.orEmpty()
                    "\n$count$pctText"
                } else ""
                text = "$dayNum$meta"
                gravity = Gravity.CENTER
                textSize = 11f
                setPadding(4, 8, 4, 8)
                setBackgroundColor(
                    when {
                        iso == mealSelectedDate.toString() -> 0x332A6F97
                        iso == today -> 0x22F0A500.toInt()
                        hasMeals -> 0x222F6F4E
                        else -> 0x00000000
                    }
                )
                setOnClickListener {
                    mealSelectedDate = LocalDate.parse(iso)
                    mealViewYear = mealSelectedDate.year
                    mealViewMonth = mealSelectedDate.monthValue
                    Thread { loadMealDayOnly() }.start()
                }
            }
            addCell(btn)
        }
    }

    private fun renderMealDay() {
        val day = mealDayData
        binding.mealList.removeAllViews()
        if (day == null) {
            binding.mealDayMeta.text = ""
            binding.mealNutrientEmpty.text = t("mealIdle")
            binding.mealNutrientEmpty.visibility = View.VISIBLE
            clearMealCharts()
            return
        }
        binding.mealDayMeta.text = t("mealTargetMeta")
            .replace("{band}", day.optString("age_band"))
            .replace("{gender}", day.optString("gender"))
            .replace("{date}", day.optString("date", mealSelectedDate.toString()))
        val meals = day.optJSONArray("meals")
        if (meals == null || meals.length() == 0) {
            binding.mealList.addView(TextView(this).apply {
                text = t("mealEmptyDay")
                textSize = 13f
                setPadding(0, 8, 0, 8)
            })
        } else {
            for (i in 0 until meals.length()) {
                val meal = meals.optJSONObject(i) ?: continue
                val row = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    setPadding(0, 4, 0, 4)
                }
                val nutrients = meal.optJSONObject("nutrients")
                val kcal = nutrients?.optDouble("每日熱量(大卡)", Double.NaN)
                val kcalText = if (kcal != null && !kcal.isNaN()) " · ${Math.round(kcal)} kcal" else ""
                val main = TextView(this).apply {
                    layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                    text = "${meal.optString("meal_slot")} · ${meal.optString("recipe_name")} × ${meal.optDouble("servings", 1.0)}$kcalText"
                    textSize = 13f
                }
                val remove = Button(this).apply {
                    text = t("mealRemove")
                    setOnClickListener {
                        val mealId = meal.optInt("meal_id", -1)
                        if (mealId >= 0) Thread { deleteMealById(mealId) }.start()
                    }
                }
                row.addView(main)
                row.addView(remove)
                binding.mealList.addView(row)
            }
        }
        val hasTargets = day.optJSONObject("targets")?.length() ?: 0
        val hasMeals = (meals?.length() ?: 0) > 0
        val monthHasMeals = run {
            val days = mealMonthData?.optJSONArray("days")
            if (days == null) false
            else (0 until days.length()).any { days.optJSONObject(it)?.optBoolean("has_meals") == true }
        }
        if (hasTargets > 0 || hasMeals || monthHasMeals) {
            binding.mealNutrientEmpty.visibility = View.GONE
            bindMealCharts(day, mealMonthData, t("mealChartEmpty"))
        } else {
            binding.mealNutrientEmpty.text = t("mealChartEmpty")
            binding.mealNutrientEmpty.visibility = View.VISIBLE
            bindMealCharts(null, null, t("mealChartEmpty"))
        }
        // Keep steps panel in sync when viewing today.
        if (day.optString("date") == todayIso()) {
            applyStepsDay(day, day.optString("steps_source", ""))
        }
    }

    private fun addSelectedMeal() {
        try {
            rememberServer()
            if (apiTokenMissing()) {
                runOnUiThread { Toast.makeText(this, t("toastStepsNeedLogin"), Toast.LENGTH_SHORT).show() }
                return
            }
            if (selectedRecipeId < 0) {
                runOnUiThread { Toast.makeText(this, t("mealPickRecipeFirst"), Toast.LENGTH_SHORT).show() }
                return
            }
            val slotIndex = binding.mealSlot.selectedItemPosition.coerceIn(0, mealSlotValues.lastIndex)
            val slot = mealSlotValues[slotIndex]
            val servings = binding.mealServings.text?.toString()?.trim()?.toDoubleOrNull() ?: 1.0
            val posted = api.addMeal(
                selectedRecipeId,
                mealSelectedDate.toString(),
                slot,
                servings,
                currentLang(),
            )
            mealDayData = unwrapDay(posted) ?: posted.optJSONObject("day") ?: mealDayData
            val month = runCatching { api.mealsMonth(mealViewYear, mealViewMonth) }.getOrNull()
            if (month != null) mealMonthData = month
            runOnUiThread {
                renderMealCalendarGrid()
                renderMealDay()
                Toast.makeText(this, t("mealAdded"), Toast.LENGTH_SHORT).show()
            }
            refreshStepsSummaryOnly()
        } catch (e: Exception) {
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    private fun deleteMealById(mealId: Int) {
        try {
            rememberServer()
            val posted = api.deleteMeal(mealId, mealSelectedDate.toString())
            mealDayData = unwrapDay(posted) ?: posted.optJSONObject("day") ?: mealDayData
            val month = runCatching { api.mealsMonth(mealViewYear, mealViewMonth) }.getOrNull()
            if (month != null) mealMonthData = month
            runOnUiThread {
                renderMealCalendarGrid()
                renderMealDay()
                Toast.makeText(this, t("mealDeleted"), Toast.LENGTH_SHORT).show()
            }
            refreshStepsSummaryOnly()
        } catch (e: Exception) {
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    private fun todayIso(): String = LocalDate.now().toString()

    private fun requestSyncSteps() {
        rememberServer()
        if (apiTokenMissing()) {
            Toast.makeText(this, t("toastStepsNeedLogin"), Toast.LENGTH_SHORT).show()
            return
        }
        // Prefer Health Connect permission flow when SDK is available.
        val client = stepsReader.healthConnectClientOrNull()
        if (client != null) {
            Thread {
                val granted = runCatching {
                    runBlocking { client.permissionController.getGrantedPermissions() }
                }.getOrDefault(emptySet())
                if (granted.containsAll(stepsReader.healthConnectPermissions())) {
                    syncStepsFromDevice(preferHc = true)
                } else {
                    runOnUiThread {
                        healthConnectPermission.launch(stepsReader.healthConnectPermissions())
                    }
                }
            }.start()
            return
        }
        if (Build.VERSION.SDK_INT >= 29 && !stepsReader.hasActivityRecognition()) {
            pendingStepsAction = "sync"
            activityRecognitionPermission.launch(Manifest.permission.ACTIVITY_RECOGNITION)
            return
        }
        Thread { syncStepsFromDevice(preferHc = false) }.start()
    }

    private fun apiTokenMissing(): Boolean = !api.hasToken()

    private fun unwrapDay(payload: JSONObject?): JSONObject? {
        if (payload == null) return null
        return payload.optJSONObject("day") ?: payload
    }

    private fun fetchStepsDay(): JSONObject? {
        val today = runCatching { api.activityToday(todayIso()) }.getOrNull()
        unwrapDay(today)?.let { return it }
        return unwrapDay(runCatching { api.mealsDay(todayIso()) }.getOrNull())
    }

    private fun syncStepsFromDevice(preferHc: Boolean = true) {
        try {
            rememberServer()
            var reading: StepsReader.Reading? = null
            if (preferHc) {
                reading = runBlocking { stepsReader.readHealthConnectToday() }
                if (reading?.steps == null && reading?.note == "permission_needed") {
                    runOnUiThread {
                        healthConnectPermission.launch(stepsReader.healthConnectPermissions())
                    }
                    return
                }
            }
            if (reading?.steps == null) {
                if (Build.VERSION.SDK_INT >= 29 && !stepsReader.hasActivityRecognition()) {
                    runOnUiThread {
                        pendingStepsAction = "sync"
                        activityRecognitionPermission.launch(Manifest.permission.ACTIVITY_RECOGNITION)
                    }
                    return
                }
                reading = stepsReader.readSensorToday()
            }
            val steps = reading?.steps
            if (steps != null) {
                val burned = reading?.burnedKcal ?: StepsReader.estimateBurned(steps)
                val posted = api.postSteps(
                    todayIso(),
                    steps,
                    reading?.source ?: "android_sensor",
                    burnedKcal = burned,
                )
                val day = unwrapDay(posted) ?: fetchStepsDay()
                runOnUiThread {
                    if (day != null) applyStepsDay(day, reading?.source ?: "android_sensor")
                    Toast.makeText(this, t("toastStepsSynced"), Toast.LENGTH_SHORT).show()
                }
            } else {
                refreshStepsSummaryOnly()
                runOnUiThread {
                    Toast.makeText(
                        this,
                        reading?.note?.ifBlank { t("stepsNote") } ?: t("stepsNote"),
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        } catch (e: Exception) {
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    private fun saveManualSteps() {
        try {
            rememberServer()
            if (apiTokenMissing()) {
                runOnUiThread { Toast.makeText(this, t("toastStepsNeedLogin"), Toast.LENGTH_SHORT).show() }
                return
            }
            val raw = binding.stepsManual.text?.toString()?.trim().orEmpty()
            val steps = raw.toIntOrNull()
            if (steps == null || steps < 0) {
                runOnUiThread { Toast.makeText(this, t("toastStepsManualEmpty"), Toast.LENGTH_SHORT).show() }
                return
            }
            val burned = StepsReader.estimateBurned(steps)
            val posted = api.postSteps(todayIso(), steps, "manual", burnedKcal = burned)
            val day = unwrapDay(posted) ?: fetchStepsDay()
            runOnUiThread {
                if (day != null) applyStepsDay(day, "manual")
                Toast.makeText(this, t("toastStepsSynced"), Toast.LENGTH_SHORT).show()
            }
        } catch (e: Exception) {
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    private fun refreshStepsSummaryOnly() {
        try {
            rememberServer()
            val day = fetchStepsDay()
            runOnUiThread {
                if (day != null) applyStepsDay(day, day.optString("steps_source", ""))
                else binding.stepsSummary.text = t("stepsSummaryIdle")
            }
        } catch (_: Exception) {
            runOnUiThread { binding.stepsSummary.text = t("stepsSummaryIdle") }
        }
    }

    private fun applyStepsDay(day: JSONObject, sourceHint: String) {
        val intake = day.optDouble("calories_intake", 0.0).let { Math.round(it).toInt() }
        val recommended = day.optInt("recommended_steps", 0)
        val actual = if (day.isNull("actual_steps")) null else day.optInt("actual_steps")
        val gap = if (day.isNull("steps_gap")) null else day.optInt("steps_gap")
        val burned = if (day.isNull("burned_kcal")) null else day.optDouble("burned_kcal", 0.0)
        val target = when {
            !day.isNull("calories_target") -> day.optDouble("calories_target", 0.0).takeIf { it > 0 }
            else -> day.optJSONObject("targets")?.optDouble("每日熱量(大卡)", 0.0)?.takeIf { it > 0 }
        }
        val source = day.optString("steps_source", sourceHint).ifBlank { sourceHint }.ifBlank { "—" }
        val burnedSafe = burned?.coerceAtLeast(0.0) ?: 0.0
        val net = Math.round((intake - burnedSafe) * 10.0) / 10.0
        val intakeLabel = if (intake > 0) {
            t("kcalBarIntake").replace("{n}", intake.toString())
        } else ""
        val burnLabel = if (burnedSafe > 0) {
            t("kcalBarBurn").replace("{n}", Math.round(burnedSafe).toString())
        } else ""
        val needLabel = if (target != null) {
            t("kcalRulerNeed").replace("{target}", Math.round(target).toString())
        } else ""
        binding.calorieRuler.bind(
            intake = intake.toFloat(),
            burn = burned?.toFloat(),
            need = target?.toFloat(),
            intakeText = intakeLabel,
            burnText = burnLabel,
            needText = needLabel,
        )
        binding.kcalNet.text = when {
            intake <= 0 && burnedSafe <= 0 -> t("kcalNetEmpty")
            target == null -> t("kcalNetNoTarget").replace("{net}", net.toString())
            else -> {
                val diff = Math.round((net - target) * 10.0) / 10.0
                when {
                    diff > 0 -> t("kcalNetOver")
                        .replace("{net}", net.toString())
                        .replace("{target}", Math.round(target).toString())
                        .replace("{over}", diff.toString())
                    diff < 0 -> t("kcalNetUnder")
                        .replace("{net}", net.toString())
                        .replace("{target}", Math.round(target).toString())
                        .replace("{under}", kotlin.math.abs(diff).toString())
                    else -> t("kcalNetEqual")
                        .replace("{net}", net.toString())
                        .replace("{target}", Math.round(target).toString())
                }
            }
        }
        if (actual == null) {
            binding.stepsSummary.text = t("stepsSummaryNoActual")
                .replace("{intake}", intake.toString())
                .replace("{recommended}", recommended.toString())
            binding.stepsRemaining.text = t("stepsRemainingUnknown")
                .replace("{recommended}", recommended.toString())
            binding.stepsProgress.progress = 0
        } else {
            val burnedText = burned?.let { String.format("%.1f", it) } ?: "—"
            val delta = burned?.let { Math.round((it - intake) * 10.0) / 10.0 }
            val deltaText = when {
                delta == null -> "—"
                delta > 0 -> "+$delta"
                else -> delta.toString()
            }
            val gapVal = gap ?: (actual - recommended)
            binding.stepsSummary.text = t("stepsSummary")
                .replace("{intake}", intake.toString())
                .replace("{actual}", actual.toString())
                .replace("{recommended}", recommended.toString())
                .replace("{gap}", gapVal.toString())
                .replace("{burned}", burnedText)
                .replace("{delta}", deltaText)
                .replace("{source}", source)
            val remain = recommended - actual
            binding.stepsRemaining.text = when {
                remain > 0 -> t("stepsRemainingNeed").replace("{n}", remain.toString())
                remain < 0 -> t("stepsRemainingDone").replace("{n}", (-remain).toString())
                else -> t("stepsRemainingExact")
            }
            val denom = maxOf(recommended, actual, 1)
            binding.stepsProgress.progress = ((100.0 * actual) / denom).toInt().coerceIn(0, 100)
            if (binding.stepsManual.text.isNullOrBlank()) {
                binding.stepsManual.setText(actual.toString())
            }
        }
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
                if (mealMonthData != null) renderMealCalendarGrid()
                if (mealDayData != null) renderMealDay()
                else if (apiTokenMissing()) showMealIdleState()
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
                    // Preserve a typed dish name; do not replace it with the country's first recipe.
                    requestRecipes(name, keepSelection = false, preserveTypedName = true)
                } else {
                    loadedCountry = ""
                    recipeLoadToken += 1
                    selectedRecipeId = -1
                    recipeRows = emptyList()
                    // Keep pending dish text when country is cleared/incomplete.
                    val typed = binding.recipePick.text?.toString()?.trim().orEmpty()
                    bindSearch(binding.recipePick, emptyList(), revealAll = true)
                    if (typed.isEmpty()) {
                        binding.recipeDetail.text = ""
                    } else {
                        // No valid country: search dish name across Recipe.xls (web parity).
                        scheduleRecipeNameSearch(typed)
                    }
                }
            }
        })
        binding.recipePick.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                synchronized(this@MainActivity) { recipeShowAllPasses = 0 }
            }
            override fun afterTextChanged(s: Editable?) {
                onRecipePickTextChanged(s?.toString().orEmpty())
            }
        })
        binding.recipeCountry.setOnFocusChangeListener { _, hasFocus ->
            if (hasFocus) showCountryMenu()
        }
        binding.recipeCountry.setOnClickListener { showCountryMenu() }
        binding.recipePick.setOnFocusChangeListener { _, hasFocus ->
            if (hasFocus) {
                revealRecipeList()
            } else {
                // Blur: ensure / fill when typed dish is not in the current list.
                maybeEnsureTypedRecipe(fromBlur = true)
            }
        }
        binding.recipePick.setOnClickListener { revealRecipeList() }
        binding.recipePick.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEARCH || actionId == EditorInfo.IME_ACTION_DONE) {
                maybeEnsureTypedRecipe(fromSubmit = true)
                true
            } else {
                false
            }
        }
        binding.recipeBodyAdvice.setOnCheckedChangeListener { _, _ ->
            refreshRecipeChoices(keepSelection = true)
        }
    }

    private fun cancelRecipeDebounce() {
        recipeNameSearchRunnable?.let { recipeUiHandler.removeCallbacks(it) }
        recipeNameSearchRunnable = null
        recipeEnsureRunnable?.let { recipeUiHandler.removeCallbacks(it) }
        recipeEnsureRunnable = null
    }

    private fun onRecipePickTextChanged(raw: String) {
        val label = raw.trim()
        cancelRecipeDebounce()
        if (label.isEmpty()) {
            (binding.recipePick.adapter as? ArrayAdapter<*>)?.filter?.filter("")
            selectedRecipeId = -1
            if (!recipeEnsureBusy) binding.recipeDetail.text = ""
            return
        }
        val exact = findRecipeByTypedName(label)
        if (exact != null) {
            showRecipeDetail(recipeLabel(exact))
            return
        }
        if (recipeEnsureBusy) {
            showRecipeEnsuringStatus()
            return
        }
        val country = selectedCountry()
        if (country.isNotEmpty()) {
            // Country list is local — show dropdown matches; ensure when nothing matches.
            (binding.recipePick.adapter as? ArrayAdapter<*>)?.filter?.filter(label) {
                if (binding.recipePick.isFocused) binding.recipePick.showDropDown()
            }
            if (recipeHasSubstringMatch(label)) {
                if (!isRecipeStatusMessage(binding.recipeDetail.text?.toString())) {
                    binding.recipeDetail.text = ""
                }
            } else {
                showRecipeSearchingStatus()
                scheduleRecipeEnsure(label)
            }
        } else {
            // No country: API name search (雞腿便當 flow), then ensure if still missing.
            showRecipeSearchingStatus()
            scheduleRecipeNameSearch(label)
        }
    }

    private fun scheduleRecipeNameSearch(typed: String) {
        val plain = recipeNamePlain(typed)
        if (plain.isEmpty()) return
        val runnable = Runnable {
            Thread { loadRecipesByName(plain) }.start()
        }
        recipeNameSearchRunnable = runnable
        recipeUiHandler.postDelayed(runnable, 280)
    }

    private fun scheduleRecipeEnsure(typed: String) {
        val plain = recipeNamePlain(typed)
        if (plain.isEmpty()) return
        val runnable = Runnable {
            if (recipeEnsureBusy) {
                recipeEnsureFollowUpName = plain
                return@Runnable
            }
            if (findRecipeByTypedName(plain) != null) return@Runnable
            if (recipeHasSubstringMatch(plain)) return@Runnable
            Thread { ensureTypedRecipe(quiet = true) }.start()
        }
        recipeEnsureRunnable = runnable
        recipeUiHandler.postDelayed(runnable, 450)
    }

    private fun maybeEnsureTypedRecipe(fromBlur: Boolean = false, fromSubmit: Boolean = false) {
        val typed = recipeNamePlain(binding.recipePick.text?.toString().orEmpty())
        if (typed.isEmpty()) return
        if (findRecipeByTypedName(typed) != null) {
            showRecipeDetail(binding.recipePick.text?.toString().orEmpty())
            return
        }
        if (!fromSubmit && !fromBlur) return
        // Substring hits: wait for an exact pick unless user explicitly submitted.
        if (!fromSubmit && recipeHasSubstringMatch(typed)) {
            showRecipeSearchingStatus()
            return
        }
        if (recipeEnsureBusy) {
            recipeEnsureFollowUpName = typed
            showRecipeEnsuringStatus()
            return
        }
        Thread { ensureTypedRecipe(quiet = fromBlur) }.start()
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
        val country = selectedCountry()
        if (country.isNotBlank() && recipeRows.isEmpty()) {
            requestRecipes(country, keepSelection = true, preserveTypedName = true)
            return
        }
        if (recipeRows.isEmpty()) {
            // Allow focusing the dish field with no country — user can type to search.
            val typed = recipeNamePlain(binding.recipePick.text?.toString().orEmpty())
            if (typed.isNotEmpty()) scheduleRecipeNameSearch(typed)
            return
        }
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
        // 0 = empty click / focus can open the full country or recipe list.
        field.threshold = 0
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

    private fun refreshSyndromeLegend() {
        bindSyndromeLegend(
            binding.bodyLegend,
            api::mediaUrl,
            http,
        ) { key -> t(key) }
    }

    private fun bindOrganSessionUi(json: JSONObject) {
        rememberJudgment(json)
        // Prefer nested scores/patterns; records may also flatten organ_* columns.
        val nestedScores = json.optJSONObject("scores")
        val nestedPatterns = json.optJSONObject("patterns")
        val scores = JSONObject()
        val patterns = JSONObject()
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
        val shownScores = withoutMaleUterus(scores)
        val shownPatterns = withoutMaleUterus(patterns)
        bindOrganScores(binding.organScores, shownScores, shownPatterns, female)
        val summaryJson = JSONObject(json.toString())
        summaryJson.put("scores", shownScores ?: JSONObject())
        summaryJson.put("patterns", shownPatterns ?: JSONObject())
        binding.sessionSummary.text = buildSessionSummary(
            summaryJson,
            female,
            t("sessionSummaryIdle"),
        ) { key ->
            when (key) {
                "face" -> t("sourceFace")
                "tongue_body" -> t("sourceTongueBody")
                "tongue_coat" -> t("sourceTongueCoat")
                "stool" -> t("sourceStool")
                "urine" -> t("sourceUrine")
                "pulse" -> t("sourcePulse")
                else -> sourceKeyLabel(key)
            }
        }
    }

    private fun bindAdvice(json: JSONObject) {
        rememberJudgment(json)
        // Prefer explicit structured queries from advice.py; fall back to URL ?q=.
        // Google Search only: theme tokens + 特殊疾病 + 今日症狀（無則五臟六腑）.
        val dietArticle = SearchLinks.ensureIntentQuery(
            json.optString("diet_query")
                .ifBlank { SearchLinks.extractQuery(json.optString("diet_url")) },
            "食譜",
        )
        val dietVideo = SearchLinks.ensureIntentQuery(
            json.optString("diet_video_query")
                .ifBlank { SearchLinks.extractQuery(json.optString("diet_video_url")) }
                .ifBlank { dietArticle },
            "食譜",
            "影片",
        )
        val acuImage = SearchLinks.ensureIntentQuery(
            json.optString("acupoint_query")
                .ifBlank { SearchLinks.extractQuery(json.optString("acupoint_url")) },
            "穴道",
            "照片",
        )
        val acuVideo = SearchLinks.ensureIntentQuery(
            json.optString("acupoint_video_query")
                .ifBlank { SearchLinks.extractQuery(json.optString("acupoint_video_url")) }
                .ifBlank { acuImage },
            "穴道",
            "影片",
        )
        // Labels only — no raw URL strings in the UI.
        SearchLinks.bindLabeledLinks(
            binding.dietLink,
            listOf(
                t("dietLinkArticles") to dietArticle,
                t("dietLinkVideos") to dietVideo,
            ),
            this,
        )
        SearchLinks.bindLabeledLinks(
            binding.acupointLink,
            listOf(
                t("acupointLinkImages") to acuImage,
                t("acupointLinkVideos") to acuVideo,
            ),
            this,
        )
    }

    private fun loadLatestAdvice() {
        try {
            rememberServer()
            val data = api.records()
            val records = data.optJSONArray("records") ?: return
            if (records.length() == 0) return
            val latest = records.getJSONObject(0)
            runOnUiThread {
                bindAdvice(latest)
                bindOrganSessionUi(latest)
                binding.bodyImage.post {
                    Thread {
                        applyBodyOverlays(
                            binding.bodyMap,
                            binding.bodyImage,
                            latest.optJSONObject("overlays"),
                            latest.optJSONObject("scores"),
                            female,
                            api::mediaUrl,
                            http,
                        )
                    }.start()
                }
            }
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
                var typedSnapshot = ""
                val latch = java.util.concurrent.CountDownLatch(1)
                runOnUiThread {
                    typedSnapshot = recipeNamePlain(binding.recipePick.text?.toString().orEmpty())
                    latch.countDown()
                }
                latch.await(1, java.util.concurrent.TimeUnit.SECONDS)
                // Do not auto-ensure on language/body refresh — only preserve typed name if keep misses.
                loadRecipes(
                    country,
                    token,
                    keepId,
                    byBody,
                    typedSnapshot,
                    preserveTypedName = false
                )
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

    private fun recipeNamePlain(label: String): String {
        return label.trim()
            .replace(Regex("\\s*★\\s*$"), "")
            .replace(Regex("（[^）]+）\\s*$"), "")
            .replace(Regex("\\s*\\([^)]+\\)\\s*$"), "")
            .trim()
    }

    private fun findRecipeByTypedName(typed: String): JSONObject? {
        val plain = recipeNamePlain(typed)
        if (plain.isEmpty()) return null
        return recipeRows.firstOrNull { recipeNamePlain(recipeLabel(it)).equals(plain, ignoreCase = true) }
            ?: recipeRows.firstOrNull { it.optString("name").trim().equals(plain, ignoreCase = true) }
    }

    private fun recipeHasSubstringMatch(typed: String): Boolean {
        val q = recipeNamePlain(typed).lowercase()
        if (q.isEmpty()) return true
        return recipeRows.any { recipeLabel(it).contains(q, ignoreCase = true) }
    }

    private fun isRecipeStatusMessage(text: String?): Boolean {
        val value = text?.trim().orEmpty()
        if (value.isEmpty()) return false
        return value == t("搜尋中", "Searching", "検索中", "검색 중")
            || value == t("搜尋建檔中", "Searching and creating data", "検索してデータを作成中", "검색하며 데이터 작성 중")
            || value.startsWith(t("建立食譜失敗", "Recipe ensure failed", "レシピ作成失敗", "레시피 작성 실패"))
    }

    private fun showRecipeSearchingStatus() {
        if (recipeEnsureBusy) {
            showRecipeEnsuringStatus()
            return
        }
        binding.recipeDetail.text = t("搜尋中", "Searching", "検索中", "검색 중")
    }

    private fun showRecipeEnsuringStatus() {
        binding.recipeDetail.text = t(
            "搜尋建檔中",
            "Searching and creating data",
            "検索してデータを作成中",
            "검색하며 데이터 작성 중"
        )
    }

    private fun recipeLabelWithCountry(row: JSONObject): String {
        val base = recipeLabel(row)
        val country = row.optString("country").trim()
        val selected = selectedCountry()
        if (country.isEmpty() || (selected.isNotEmpty() && selected == country)) return base
        return "${recipeNamePlain(base)}（$country）"
    }

    private fun ensureTypedRecipe(quiet: Boolean = false) {
        val country = binding.recipeCountry.text?.toString()?.trim().orEmpty().let {
            if (it.isNotEmpty() && it in countryNames) it else it.ifBlank { "" }
        }
        val name = recipeNamePlain(binding.recipePick.text?.toString().orEmpty())
        if (name.isBlank()) {
            if (!quiet) {
                runOnUiThread {
                    Toast.makeText(this, "請先輸入要建立的食譜名稱", Toast.LENGTH_SHORT).show()
                }
            }
            return
        }
        val existing = findRecipeByTypedName(name)
        val needsFill = existing != null && listOf("recipe", "method", "benefit", "nutrient")
            .any { key -> existing.optString(key).trim().isEmpty() }
        if (existing != null && !needsFill) {
            runOnUiThread {
                selectedRecipeId = existing.optInt("id", -1)
                val label = recipeLabel(existing)
                binding.recipePick.setText(label, false)
                showRecipeDetail(label)
            }
            return
        }
        val token = ++recipeEnsureToken
        recipeEnsureBusy = true
        try {
            rememberServer()
            runOnUiThread {
                cancelRecipeDebounce()
                // Keep the multilingual typed name visible while researching.
                binding.recipePick.setText(name, false)
                showRecipeEnsuringStatus()
                if (!quiet) Toast.makeText(this, "建立食譜中…", Toast.LENGTH_SHORT).show()
            }
            // Re-read country in case user filled it after ensure started.
            val ensureCountry = binding.recipeCountry.text?.toString()?.trim().orEmpty().let {
                when {
                    it.isNotEmpty() && it in countryNames -> it
                    it.isNotEmpty() -> it
                    else -> country
                }
            }
            val data = api.ensureRecipe(ensureCountry, name, currentLang())
            if (token != recipeEnsureToken) return
            runOnUiThread {
                if (token != recipeEnsureToken) return@runOnUiThread
                val recipe = data.optJSONObject("recipe")
                val shown = recipe?.optString("name")?.ifBlank { name } ?: name
                if (!quiet || data.optBoolean("created", false)) {
                    Toast.makeText(
                        this,
                        if (data.optBoolean("created", true)) "已寫入共用食譜庫：$shown（網站／App 同步）"
                        else "已更新／取得：$shown",
                        Toast.LENGTH_LONG
                    ).show()
                }
                if (recipe != null) {
                    val id = recipe.optInt("id", -1)
                    if (id >= 0) selectedRecipeId = id
                    // Prefer server localized name; fall back to the typed multilingual name.
                    val label = recipe.optString("name").ifBlank { name }.let { n ->
                        if (recipe.optBoolean("benefit_match")) "$n ★" else n
                    }
                    binding.recipePick.setText(label, false)
                    val resolvedCountry = recipe.optString("country").ifBlank {
                        binding.recipeCountry.text?.toString()?.trim().orEmpty()
                    }
                    if (resolvedCountry.isNotEmpty()) {
                        if (resolvedCountry !in countryNames) {
                            countryNames = listOf(resolvedCountry) + countryNames
                            bindSearch(binding.recipeCountry, countryNames, prefix = true)
                        }
                        binding.recipeCountry.setText(resolvedCountry, false)
                        loadedCountry = resolvedCountry
                    }
                    // Merge created row into local list so detail can render immediately.
                    if (id < 0 || recipeRows.none { it.optInt("id", -1) == id }) {
                        recipeRows = listOf(recipe) + recipeRows
                    }
                    val labels = recipeRows.map {
                        if (selectedCountry().isEmpty()) recipeLabelWithCountry(it) else recipeLabel(it)
                    }
                    bindSearch(binding.recipePick, labels, revealAll = true)
                    showRecipeDetail(label)
                }
                refreshRecipeChoices(keepSelection = true)
            }
        } catch (e: Exception) {
            if (token != recipeEnsureToken) return
            runOnUiThread {
                binding.recipeDetail.text = e.message
                    ?: t("建立食譜失敗", "Recipe ensure failed", "レシピ作成失敗", "레시피 작성 실패")
                Toast.makeText(this, e.message, Toast.LENGTH_LONG).show()
            }
        } finally {
            if (token == recipeEnsureToken) {
                recipeEnsureBusy = false
                val followUp = recipeEnsureFollowUpName
                recipeEnsureFollowUpName = null
                if (!followUp.isNullOrBlank() && findRecipeByTypedName(followUp) == null) {
                    runOnUiThread {
                        binding.recipePick.setText(followUp, false)
                        Thread { ensureTypedRecipe(quiet = true) }.start()
                    }
                }
            }
        }
    }

    private fun requestRecipes(
        countryName: String,
        keepSelection: Boolean = false,
        preserveTypedName: Boolean = false
    ) {
        if (countryName.isBlank()) return
        val keepId = if (keepSelection) selectedRecipeId else -1
        val typedName = recipeNamePlain(binding.recipePick.text?.toString().orEmpty())
        if (!keepSelection && !preserveTypedName) selectedRecipeId = -1
        val token = ++recipeLoadToken
        loadedCountry = countryName
        val byBody = binding.recipeBodyAdvice.isChecked
        // Only auto-ensure when caller asked (country just chosen with a pending dish).
        Thread { loadRecipes(countryName, token, keepId, byBody, typedName, preserveTypedName) }.start()
    }

    private fun loadRecipes(
        countryName: String,
        token: Int,
        keepId: Int,
        byBody: Boolean,
        typedName: String = "",
        preserveTypedName: Boolean = false
    ) {
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
                val typedMatch = if (typedName.isNotEmpty()) {
                    rows.firstOrNull { recipeNamePlain(recipeLabel(it)).equals(typedName, ignoreCase = true) }
                        ?: rows.firstOrNull { it.optString("name").trim().equals(typedName, ignoreCase = true) }
                } else null
                val chosen = kept ?: typedMatch
                if (chosen != null) {
                    val label = recipeLabel(chosen)
                    binding.recipePick.setText(label, false)
                    showRecipeDetail(label)
                } else if (typedName.isNotEmpty()) {
                    // Keep pending dish — never silently switch to 蛋餅 / first country recipe.
                    selectedRecipeId = -1
                    binding.recipePick.setText(typedName, false)
                    if (preserveTypedName) {
                        if (recipeEnsureBusy) {
                            recipeEnsureFollowUpName = typedName
                            showRecipeEnsuringStatus()
                        } else {
                            showRecipeEnsuringStatus()
                            Thread { ensureTypedRecipe(quiet = true) }.start()
                        }
                    } else if (!recipeEnsureBusy) {
                        showRecipeSearchingStatus()
                        scheduleRecipeEnsure(typedName)
                    }
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
                // After country chosen: always open full recipe list for that country.
                if (rows.isNotEmpty()) {
                    binding.recipePick.post {
                        synchronized(this@MainActivity) { recipeShowAllPasses = 2 }
                        revealRecipeList()
                    }
                }
            }
        } catch (e: Exception) {
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    /** Cross-country dish search when no country is selected (web loadRecipesByName). */
    private fun loadRecipesByName(name: String) {
        val plain = recipeNamePlain(name)
        if (plain.isEmpty()) return
        val token = ++recipeLoadToken
        val byBody = binding.recipeBodyAdvice.isChecked
        try {
            rememberServer()
            val scores = if (judgmentReady) lastScoresJson else ""
            val patterns = if (judgmentReady) lastPatternsJson else ""
            val data = api.recipes(
                country = "",
                lang = currentLang(),
                scores = scores,
                patterns = patterns,
                female = female,
                byBody = byBody,
                name = plain,
            )
            if (token != recipeLoadToken) return
            val arr = data.optJSONArray("recipes") ?: JSONArray()
            val rows = ArrayList<JSONObject>(arr.length())
            val labels = ArrayList<String>(arr.length())
            for (i in 0 until arr.length()) {
                val row = arr.optJSONObject(i) ?: continue
                rows.add(row)
                labels.add(recipeLabelWithCountry(row))
            }
            recipeRows = rows
            runOnUiThread {
                if (token != recipeLoadToken) return@runOnUiThread
                // Country may have been filled while the name search was in flight.
                if (selectedCountry().isNotEmpty()) return@runOnUiThread
                bindSearch(binding.recipePick, labels, revealAll = true)
                val exact = findRecipeByTypedName(plain)
                if (exact != null) {
                    val label = recipeLabelWithCountry(exact)
                    binding.recipePick.setText(label, false)
                    val country = exact.optString("country").trim()
                    if (country.isNotEmpty()) {
                        if (country !in countryNames) {
                            countryNames = listOf(country) + countryNames
                            bindSearch(binding.recipeCountry, countryNames, prefix = true)
                        }
                        binding.recipeCountry.setText(country, false)
                        loadedCountry = country
                    }
                    showRecipeDetail(recipeLabel(exact))
                    return@runOnUiThread
                }
                // Keep typed multilingual name; open matches if any, else ensure/create.
                binding.recipePick.setText(plain, false)
                if (rows.isNotEmpty()) {
                    if (!recipeEnsureBusy) binding.recipeDetail.text = ""
                    binding.recipePick.post { revealRecipeList() }
                } else if (!recipeEnsureBusy) {
                    showRecipeSearchingStatus()
                    scheduleRecipeEnsure(plain)
                }
            }
        } catch (e: Exception) {
            if (token != recipeLoadToken) return
            runOnUiThread { Toast.makeText(this, e.message, Toast.LENGTH_LONG).show() }
        }
    }

    private fun recipeLabel(row: JSONObject): String {
        val star = if (row.optBoolean("benefit_match")) " ★" else ""
        return row.optString("name") + star
    }

    private fun showRecipeDetail(label: String) {
        val plain = recipeNamePlain(label)
        val row = when {
            plain.isEmpty() -> null
            else -> findRecipeByTypedName(plain)
                ?: recipeRows.firstOrNull { recipeLabel(it) == label }
                ?: recipeRows.firstOrNull { recipeLabelWithCountry(it) == label }
        }
        if (row == null) {
            selectedRecipeId = -1
            // Keep ensuring/search status; never leave another dish's detail under this name.
            if (!recipeEnsureBusy && !isRecipeStatusMessage(binding.recipeDetail.text?.toString())) {
                binding.recipeDetail.text = ""
            }
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
        // Do not paste raw search URLs here — clickable labels live in dietLink / acupointLink.
        return "匿名紀錄已寫入 MySQL（教學參考，非診斷）\n" +
            "食療：" + withoutMaleUterusText(json.optString("diet_advice")) + "\n" +
            t("dietLinkHint") + "\n" +
            "分數：" + shownScores + "\n" +
            "證型：" + healthyPatterns(shownScores, shownPatterns)
    }
}
