package com.tube.healthing

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Path
import android.media.ExifInterface
import android.util.AttributeSet
import android.view.View
import java.io.ByteArrayOutputStream
import java.io.File
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * Yellow tongue window, same fractions as the web stage.
 * Crop is the rectangle from the teeth line to the bottom of the arc, full frame width.
 * PreviewView uses FILL_CENTER; the saved JPEG is that on-screen rectangle, mirrored like the front preview.
 */
object TongueFrame {
    const val LEFT = 0.36f
    const val TOP = 0.22f
    const val WIDTH = 0.28f
    const val HEIGHT = 0.52f
    const val TEETH_Y = 12f / 160f

    fun cropFileToYellowFrame(file: File, viewW: Int, viewH: Int) {
        if (viewW < 2 || viewH < 2 || !file.isFile) return
        val decoded = BitmapFactory.decodeFile(file.absolutePath) ?: return
        val uprightBmp = upright(decoded, file)
        val mirrored = mirrorHorizontal(uprightBmp)
        val cropped = cropVisibleFrame(mirrored, viewW, viewH) ?: return
        val bytes = ByteArrayOutputStream()
        if (!cropped.compress(Bitmap.CompressFormat.JPEG, 92, bytes)) return
        file.writeBytes(bytes.toByteArray())
    }

    fun cropVisibleFrame(bitmap: Bitmap, viewW: Int, viewH: Int): Bitmap? {
        val bw = bitmap.width.toFloat()
        val bh = bitmap.height.toFloat()
        if (bw < 2f || bh < 2f || viewW < 2 || viewH < 2) return null
        val scale = max(viewW / bw, viewH / bh)
        if (scale <= 0f) return null
        val offX = (viewW - bw * scale) / 2f
        val offY = (viewH - bh * scale) / 2f
        val frameLeft = viewW * LEFT
        val frameTop = viewH * TOP
        val frameW = viewW * WIDTH
        val frameH = viewH * HEIGHT
        val x0 = (((frameLeft - offX) / scale)).roundToInt().coerceIn(0, bitmap.width - 1)
        val y0 = (((frameTop + frameH * TEETH_Y - offY) / scale)).roundToInt().coerceIn(0, bitmap.height - 1)
        val x1 = (((frameLeft + frameW - offX) / scale)).roundToInt().coerceIn(x0 + 1, bitmap.width)
        val y1 = (((frameTop + frameH - offY) / scale)).roundToInt().coerceIn(y0 + 1, bitmap.height)
        if (x1 <= x0 || y1 <= y0) return null
        return Bitmap.createBitmap(bitmap, x0, y0, x1 - x0, y1 - y0)
    }

    private fun mirrorHorizontal(bitmap: Bitmap): Bitmap {
        val matrix = Matrix().apply { postScale(-1f, 1f) }
        return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
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

class TongueGuideView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = Color.rgb(255, 204, 0)
        strokeWidth = 3f * resources.displayMetrics.density
        strokeCap = Paint.Cap.ROUND
    }

    override fun onDraw(canvas: Canvas) {
        val frameLeft = width * TongueFrame.LEFT
        val frameTop = height * TongueFrame.TOP
        val frameW = width * TongueFrame.WIDTH
        val frameH = height * TongueFrame.HEIGHT
        val frameRight = frameLeft + frameW
        val frameBottom = frameTop + frameH
        val topR = 8f * resources.displayMetrics.density
        val path = Path()
        path.addRoundRect(
            frameLeft,
            frameTop,
            frameRight,
            frameBottom,
            floatArrayOf(
                topR, topR,
                topR, topR,
                frameW * 0.5f, frameH * 0.4f,
                frameW * 0.5f, frameH * 0.4f
            ),
            Path.Direction.CW
        )
        canvas.drawPath(path, stroke)
        val y = frameTop + frameH * TongueFrame.TEETH_Y
        canvas.drawLine(frameLeft + frameW * 0.06f, y, frameLeft + frameW * 0.94f, y, stroke)
    }
}
