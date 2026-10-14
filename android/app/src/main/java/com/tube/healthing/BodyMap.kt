package com.tube.healthing

import android.graphics.BitmapFactory
import android.graphics.BlendMode
import android.graphics.Color
import android.os.Build
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.TextView
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject

data class OrganSpot(val key: String, val name: String, val x: Float, val y: Float, val femaleOnly: Boolean = false)

val ORGAN_SPOTS = listOf(
    OrganSpot("lung", "肺", 0.44f, 0.315f),
    OrganSpot("lung", "肺", 0.56f, 0.315f),
    OrganSpot("heart", "心", 0.535f, 0.355f),
    OrganSpot("liver", "肝", 0.44f, 0.415f),
    OrganSpot("gallbladder", "膽", 0.415f, 0.445f),
    OrganSpot("spleen", "脾", 0.565f, 0.435f),
    OrganSpot("large_intestine", "大腸", 0.38f, 0.52f),
    OrganSpot("large_intestine", "大腸", 0.62f, 0.52f),
    OrganSpot("small_intestine", "小腸", 0.50f, 0.54f),
    OrganSpot("kidney", "腎", 0.44f, 0.61f),
    OrganSpot("kidney", "腎", 0.56f, 0.61f),
    OrganSpot("bladder", "膀胱", 0.50f, 0.645f),
    OrganSpot("uterus", "子宮", 0.50f, 0.625f, femaleOnly = true),
)

fun applyBodyOverlays(
    container: FrameLayout,
    bodyView: ImageView,
    overlays: JSONObject?,
    female: Boolean,
    mediaUrl: (String) -> String,
    client: OkHttpClient
) {
    val toRemove = mutableListOf<android.view.View>()
    for (i in 0 until container.childCount) {
        val child = container.getChildAt(i)
        if (child !== bodyView) toRemove.add(child)
    }
    toRemove.forEach { container.removeView(it) }
    if (overlays == null) return
    val w = bodyView.width
    val h = bodyView.height
    if (w == 0 || h == 0) return
    ORGAN_SPOTS.forEach { spot ->
        if (spot.femaleOnly && !female) return@forEach
        val file = overlays.optString(spot.key, "")
        if (file.isBlank() || file == "null") return@forEach
        val req = Request.Builder().url(mediaUrl(file)).build()
        client.newCall(req).execute().use { resp ->
            val bytes = resp.body?.bytes() ?: return@forEach
            val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: return@forEach
            bodyView.post {
                val size = (w * 0.13f).toInt()
                val img = ImageView(container.context)
                img.setImageBitmap(bmp)
                img.adjustViewBounds = true
                img.setBackgroundColor(Color.TRANSPARENT)
                if (Build.VERSION.SDK_INT >= 29) {
                    val paint = android.graphics.Paint()
                    paint.blendMode = BlendMode.SCREEN
                    img.setLayerType(ImageView.LAYER_TYPE_HARDWARE, paint)
                }
                val lp = FrameLayout.LayoutParams(size, size)
                img.x = w * spot.x - size / 2f
                img.y = h * spot.y - size / 2f
                container.addView(img, lp)
                val label = TextView(container.context)
                label.text = spot.name
                label.textSize = 10f
                label.x = w * spot.x - 20
                label.y = h * spot.y + size / 3f
                container.addView(label, ViewGroup.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT))
            }
        }
    }
}
