package com.tube.healthing

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.media.ExifInterface
import android.util.AttributeSet
import android.view.View
import java.io.ByteArrayOutputStream
import java.io.File
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * Face preview is drawn at [PREVIEW_ZOOM] (view scale around the center).
 * The saved JPEG is that same visible region, mirrored like the front preview.
 *
 * 12-cell grid matches analysis.crop_cell: 3 columns × 4 rows.
 * Bottom row is 10 | 12 lips | 11. Guides use viewBox 300×400 (cell 100×100):
 * cell 4 center (50,150), cell 6 center (250,150),
 * cell 8 vertical middle (150,250), cell 12 center (150,350).
 *
 * The on-screen guides stay on that visible frame. The JPEG for face color
 * moves the face up by 1/4 of a cell and draws it at [FACE_SCALE] (0.9×).
 */
object FaceFrame {
    const val PREVIEW_ZOOM = 2f

    /** Face size in the color JPEG relative to the yellow-guide window. */
    const val FACE_SCALE = 0.9f

    /** Cells to move the face up. One cell is 1/4 of the analysis frame. */
    const val FACE_SHIFT_UP_CELLS = 0.25f

    fun cropFileToVisiblePreview(file: File, viewW: Int, viewH: Int) {
        if (viewW < 2 || viewH < 2 || !file.isFile) return
        val decoded = BitmapFactory.decodeFile(file.absolutePath) ?: return
        val uprightBmp = upright(decoded, file)
        val mirrored = mirrorHorizontal(uprightBmp)
        val cropped = cropVisibleZoom(mirrored, viewW, viewH) ?: return
        val bytes = ByteArrayOutputStream()
        if (!cropped.compress(Bitmap.CompressFormat.JPEG, 92, bytes)) return
        file.writeBytes(bytes.toByteArray())
    }

    /**
     * Color-analysis crop: the visible preview (what the yellow guides sit on),
     * expanded so the face is 0.9×, then sampled lower so the face sits
     * 1/4 of a cell higher. Guide drawing is unchanged.
     */
    fun cropVisibleZoom(bitmap: Bitmap, viewW: Int, viewH: Int): Bitmap? {
        val bw = bitmap.width.toFloat()
        val bh = bitmap.height.toFloat()
        if (bw < 2f || bh < 2f || viewW < 2 || viewH < 2) return null
        val fit = max(viewW / bw, viewH / bh)
        if (fit <= 0f) return null
        val offX = (viewW - bw * fit) / 2f
        val offY = (viewH - bh * fit) / 2f
        val margin = (1f - 1f / PREVIEW_ZOOM) / 2f
        val visLeft = viewW * margin
        val visTop = viewH * margin
        val visRight = viewW * (1f - margin)
        val visBottom = viewH * (1f - margin)
        val visW = visRight - visLeft
        val visH = visBottom - visTop
        val scaledW = visW / FACE_SCALE
        val scaledH = visH / FACE_SCALE
        val cx = (visLeft + visRight) / 2f
        val cy = (visTop + visBottom) / 2f
        val shiftDown = scaledH * (FACE_SHIFT_UP_CELLS / 4f)
        val left = cx - scaledW / 2f
        val top = cy - scaledH / 2f + shiftDown
        val right = left + scaledW
        val bottom = top + scaledH
        val x0 = ((left - offX) / fit).roundToInt().coerceIn(0, bitmap.width - 1)
        val y0 = ((top - offY) / fit).roundToInt().coerceIn(0, bitmap.height - 1)
        val x1 = ((right - offX) / fit).roundToInt().coerceIn(x0 + 1, bitmap.width)
        val y1 = ((bottom - offY) / fit).roundToInt().coerceIn(y0 + 1, bitmap.height)
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

class FaceGuideView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = Color.rgb(255, 204, 0)
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val eyePath = Path().apply {
        moveTo(15f, 50f)
        quadTo(33f, 36f, 57f, 38f)
        quadTo(77f, 40f, 85f, 50f)
        quadTo(77f, 60f, 57f, 62f)
        quadTo(33f, 64f, 15f, 50f)
        close()
    }
    private val eyeOval = RectF(41.5f, 42.5f, 58.5f, 57.5f)
    private val nosePath = Path().apply {
        moveTo(50f, 6f)
        cubicTo(46f, 24f, 44f, 42f, 42f, 56f)
        cubicTo(40f, 68f, 36f, 74f, 28f, 78f)
        cubicTo(22f, 81f, 20f, 86f, 26f, 88f)
        cubicTo(34f, 91f, 44f, 86f, 50f, 80f)
        cubicTo(56f, 86f, 66f, 91f, 74f, 88f)
        cubicTo(80f, 86f, 78f, 81f, 72f, 78f)
        cubicTo(64f, 74f, 60f, 68f, 58f, 56f)
        cubicTo(56f, 42f, 54f, 24f, 50f, 6f)
        close()
    }
    private val lipUpper = Path().apply {
        moveTo(12f, 50f)
        quadTo(24f, 36f, 34f, 36f)
        quadTo(44f, 36f, 50f, 44f)
        quadTo(56f, 36f, 66f, 36f)
        quadTo(76f, 36f, 88f, 50f)
        quadTo(70f, 56f, 50f, 54f)
        quadTo(30f, 56f, 12f, 50f)
        close()
    }
    private val lipLower = Path().apply {
        moveTo(16f, 54f)
        quadTo(50f, 52f, 84f, 54f)
        quadTo(72f, 74f, 50f, 78f)
        quadTo(28f, 74f, 16f, 54f)
        close()
    }

    init {
        setWillNotDraw(false)
    }

    override fun onDraw(canvas: Canvas) {
        if (width < 2 || height < 2) return
        stroke.strokeWidth = 3f * resources.displayMetrics.density
        val inset = stroke.strokeWidth / 2f
        val radius = 18f * resources.displayMetrics.density
        canvas.drawRoundRect(inset, inset, width - inset, height - inset, radius, radius, stroke)

        canvas.save()
        canvas.scale(width / 300f, height / 400f)
        stroke.strokeWidth = 2.4f
        drawEye(canvas, 0f, 100f, mirror = false)
        drawEye(canvas, 300f, 100f, mirror = true)
        canvas.save()
        // Nose path y is 6–88.90 (mid 47.45). Mark center is y=200, half a cell above the cell 8 midline.
        canvas.translate(100f, 152.55f)
        canvas.drawPath(nosePath, stroke)
        canvas.restore()
        canvas.save()
        canvas.translate(100f, 293f)
        canvas.drawPath(lipUpper, stroke)
        canvas.drawPath(lipLower, stroke)
        canvas.restore()
        canvas.restore()
    }

    private fun drawEye(canvas: Canvas, tx: Float, ty: Float, mirror: Boolean) {
        canvas.save()
        canvas.translate(tx, ty)
        if (mirror) canvas.scale(-1f, 1f)
        canvas.drawPath(eyePath, stroke)
        canvas.drawOval(eyeOval, stroke)
        canvas.restore()
    }
}
