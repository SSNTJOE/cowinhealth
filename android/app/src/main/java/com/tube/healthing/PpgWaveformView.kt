package com.tube.healthing

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.util.AttributeSet
import android.view.View

/** Scrolling PPG waveform for no-flash heart-rate UI. */
class PpgWaveformView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 3f * resources.displayMetrics.density
        color = Color.parseColor("#E53935")
        strokeJoin = Paint.Join.ROUND
        strokeCap = Paint.Cap.ROUND
    }
    private val grid = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 1f * resources.displayMetrics.density
        color = Color.parseColor("#33FFFFFF")
    }
    private val path = Path()
    private val samples = FloatArray(CAPACITY) { 0.5f }
    private var write = 0
    private var filled = 0

    fun push(normalized: Float) {
        samples[write % CAPACITY] = normalized.coerceIn(0f, 1f)
        write++
        if (filled < CAPACITY) filled++
        postInvalidateOnAnimation()
    }

    fun clear() {
        write = 0
        filled = 0
        samples.fill(0.5f)
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val w = width.toFloat()
        val h = height.toFloat()
        if (w <= 0f || h <= 0f) return
        canvas.drawLine(0f, h * 0.5f, w, h * 0.5f, grid)
        if (filled < 2) return
        path.reset()
        val n = filled.coerceAtMost(CAPACITY)
        val start = if (filled < CAPACITY) 0 else write
        for (i in 0 until n) {
            val v = samples[(start + i) % CAPACITY]
            val x = i * w / (n - 1).coerceAtLeast(1)
            val y = h - v * h
            if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        canvas.drawPath(path, paint)
    }

    companion object {
        private const val CAPACITY = 160
    }
}
