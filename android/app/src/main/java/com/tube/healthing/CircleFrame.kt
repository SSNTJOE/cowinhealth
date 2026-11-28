package com.tube.healthing

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import java.io.ByteArrayOutputStream
import java.io.File
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Yellow-circle ROI crop for stool / urine — same idea as web [captureCircleFrame].
 *
 * Preview is drawn at [PREVIEW_ZOOM] around center; [CircleGuideView] draws a circle of
 * radius [RADIUS_FRAC] × min(view). Without this crop the full JPEG goes to Lab, so
 * toilet porcelain / shadows dominate the dark cluster and re-shots stick on the same
 * class (e.g. 黑色／瀝青色) even when the circle content changed.
 */
object CircleFrame {
    const val PREVIEW_ZOOM = 2f

    /** Must match [CircleGuideView] radius = min(w,h) * 0.32f. */
    const val RADIUS_FRAC = 0.32f

    /** Lab only needs a small circle; keep upload snappy on phone Wi‑Fi. */
    private const val MAX_SIDE = 640
    private const val JPEG_QUALITY = 72

    fun cropFileToYellowCircle(file: File, viewW: Int, viewH: Int) {
        if (viewW < 2 || viewH < 2 || !file.isFile) return
        val decoded = BitmapFactory.decodeFile(file.absolutePath) ?: return
        val uprightBmp = upright(decoded, file)
        val cropped = cropVisibleCircle(uprightBmp, viewW, viewH) ?: return
        val scaled = downscale(cropped, MAX_SIDE)
        val bytes = ByteArrayOutputStream()
        if (!scaled.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, bytes)) return
        file.writeBytes(bytes.toByteArray())
        if (scaled !== cropped && scaled !== uprightBmp) scaled.recycle()
        if (cropped !== uprightBmp) cropped.recycle()
        if (uprightBmp !== decoded) uprightBmp.recycle()
        decoded.recycle()
    }

    /**
     * Map the on-screen yellow circle through preview zoom back to the captured
     * FILL_CENTER frame, then take the inscribed square (Lab expects a circle crop).
     * Rear camera: no horizontal mirror (unlike front face/tongue).
     */
    fun cropVisibleCircle(bitmap: Bitmap, viewW: Int, viewH: Int): Bitmap? {
        val bw = bitmap.width.toFloat()
        val bh = bitmap.height.toFloat()
        if (bw < 2f || bh < 2f || viewW < 2 || viewH < 2) return null
        val fit = max(viewW / bw, viewH / bh)
        if (fit <= 0f) return null
        val offX = (viewW - bw * fit) / 2f
        val offY = (viewH - bh * fit) / 2f
        val cx = viewW / 2f
        val cy = viewH / 2f
        val guideR = min(viewW, viewH) * RADIUS_FRAC
        // Overlay is not scaled; preview content is. Un-zoom circle into FILL_CENTER space.
        val contentR = guideR / PREVIEW_ZOOM
        val left = cx - contentR
        val top = cy - contentR
        val right = cx + contentR
        val bottom = cy + contentR
        val x0 = ((left - offX) / fit).roundToInt().coerceIn(0, bitmap.width - 1)
        val y0 = ((top - offY) / fit).roundToInt().coerceIn(0, bitmap.height - 1)
        val x1 = ((right - offX) / fit).roundToInt().coerceIn(x0 + 1, bitmap.width)
        val y1 = ((bottom - offY) / fit).roundToInt().coerceIn(y0 + 1, bitmap.height)
        if (x1 <= x0 || y1 <= y0) return null
        return Bitmap.createBitmap(bitmap, x0, y0, x1 - x0, y1 - y0)
    }

    private fun downscale(bitmap: Bitmap, maxSide: Int): Bitmap {
        val w = bitmap.width
        val h = bitmap.height
        val longest = max(w, h)
        if (longest <= maxSide) return bitmap
        val scale = maxSide.toFloat() / longest.toFloat()
        val nw = max(1, (w * scale).roundToInt())
        val nh = max(1, (h * scale).roundToInt())
        return Bitmap.createScaledBitmap(bitmap, nw, nh, true)
    }

    private fun upright(bitmap: Bitmap, file: File): Bitmap {
        val orientation = ExifInterface(file.absolutePath).getAttributeInt(
            ExifInterface.TAG_ORIENTATION,
            ExifInterface.ORIENTATION_NORMAL
        )
        val matrix = Matrix()
        when (orientation) {
            ExifInterface.ORIENTATION_ROTATE_90 -> matrix.postRotate(90f)
            ExifInterface.ORIENTATION_ROTATE_180 -> matrix.postRotate(180f)
            ExifInterface.ORIENTATION_ROTATE_270 -> matrix.postRotate(270f)
            ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> matrix.postScale(-1f, 1f)
            ExifInterface.ORIENTATION_FLIP_VERTICAL -> matrix.postScale(1f, -1f)
            ExifInterface.ORIENTATION_TRANSPOSE -> {
                matrix.postRotate(90f)
                matrix.postScale(-1f, 1f)
            }
            ExifInterface.ORIENTATION_TRANSVERSE -> {
                matrix.postRotate(270f)
                matrix.postScale(-1f, 1f)
            }
            else -> return bitmap
        }
        return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
    }
}
