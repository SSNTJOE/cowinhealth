package com.tube.healthing

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View
import kotlin.math.min

/** Circular progress ring over the camera preview. */
class PpgRingView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {
    private val track = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 8f * resources.displayMetrics.density
        color = Color.parseColor("#44FFFFFF")
        strokeCap = Paint.Cap.ROUND
    }
    private val progressPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 8f * resources.displayMetrics.density
        color = Color.parseColor("#E53935")
        strokeCap = Paint.Cap.ROUND
    }
    private val oval = RectF()
    private var progress = 0f

    fun setProgress(fraction: Float) {
        progress = fraction.coerceIn(0f, 1f)
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val pad = progressPaint.strokeWidth
        val size = min(width, height).toFloat()
        val left = (width - size) / 2f + pad
        val top = (height - size) / 2f + pad
        oval.set(left, top, left + size - 2 * pad, top + size - 2 * pad)
        canvas.drawArc(oval, -90f, 360f, false, track)
        if (progress > 0f) {
            canvas.drawArc(oval, -90f, 360f * progress, false, progressPaint)
        }
    }
}
