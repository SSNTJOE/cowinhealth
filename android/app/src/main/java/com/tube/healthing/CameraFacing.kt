package com.tube.healthing

import android.content.Context
import androidx.camera.core.CameraSelector

/**
 * Per capture-type camera lens settings.
 *
 * Defaults live in [R.string] / res/values/config.xml and are copied into
 * SharedPreferences ("healthing") on first use so they persist as app settings.
 *
 * Keys: camera_facing_face, camera_facing_tongue, camera_facing_stool, camera_facing_urine
 * Values: "front" | "back"
 */
object CameraFacing {
    const val PREFS_NAME = "healthing"

    const val FACE = "face"
    const val TONGUE = "tongue"
    const val STOOL = "stool"
    const val URINE = "urine"

    const val FRONT = "front"
    const val BACK = "back"

    private val resourceIds = mapOf(
        FACE to R.string.camera_facing_face,
        TONGUE to R.string.camera_facing_tongue,
        STOOL to R.string.camera_facing_stool,
        URINE to R.string.camera_facing_urine
    )

    fun prefKey(kind: String): String = "camera_facing_${normalize(kind)}"

    /** Write resource defaults into prefs when a key is missing. */
    fun ensureDefaults(context: Context) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val editor = prefs.edit()
        var changed = false
        for ((kind, resId) in resourceIds) {
            val key = prefKey(kind)
            if (!prefs.contains(key)) {
                editor.putString(key, context.getString(resId))
                changed = true
            }
        }
        if (changed) editor.apply()
    }

    fun normalize(kind: String): String = when (kind.lowercase()) {
        TONGUE -> TONGUE
        STOOL -> STOOL
        URINE -> URINE
        else -> FACE
    }

    /** "front" or "back" for this capture type (prefs, then config.xml). */
    fun facingString(context: Context, kind: String): String {
        val key = normalize(kind)
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val stored = prefs.getString(prefKey(key), null)
        if (!stored.isNullOrBlank()) return normalizeFacing(stored)
        val resId = resourceIds[key] ?: R.string.camera_facing_face
        return normalizeFacing(context.getString(resId))
    }

    fun isFront(context: Context, kind: String): Boolean =
        facingString(context, kind) == FRONT

    fun selector(context: Context, kind: String): CameraSelector =
        if (isFront(context, kind)) {
            CameraSelector.DEFAULT_FRONT_CAMERA
        } else {
            CameraSelector.DEFAULT_BACK_CAMERA
        }

    private fun normalizeFacing(raw: String): String {
        val v = raw.trim().lowercase()
        return when (v) {
            "rear", "back", "0" -> BACK
            else -> FRONT
        }
    }
}
