package com.tube.healthing

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View
import kotlin.math.max
import kotlin.math.min

/**
 * Daily calorie need spans ~half the track width.
 * Yellow (60% α) = intake L→R; green (60% α) = burn from yellow tip R→L overlay.
 * Bars never exceed the view; burn label lifts above when it cannot fit inside green.
 */
class CalorieRulerView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0,
) : View(context, attrs, defStyleAttr) {

    var intakeKcal: Float = 0f
        set(value) {
            field = max(0f, value)
            invalidate()
        }
    var burnKcal: Float = 0f
        set(value) {
            field = max(0f, value)
            invalidate()
        }
    var needKcal: Float = 0f
        set(value) {
            field = max(0f, value)
            invalidate()
        }
    var intakeLabel: String = ""
        set(value) {
            field = value
            invalidate()
        }
    var burnLabel: String = ""
        set(value) {
            field = value
            invalidate()
        }
    var needCaption: String = ""
        set(value) {
            field = value
            invalidate()
        }

    private val trackPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0x12000000
        style = Paint.Style.FILL
    }
    private val intakePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0x99F0C020.toInt() // yellow @ ~60%
        style = Paint.Style.FILL
    }
    private val burnPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0x992EA05A.toInt() // green @ ~60%
        style = Paint.Style.FILL
    }
    private val needMarkPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xBF282828.toInt()
        strokeWidth = dp(2f)
    }
    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xEB141E14.toInt()
        textSize = sp(11f)
        isFakeBoldText = true
    }
    private val burnAbovePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF1F6B3F.toInt()
        textSize = sp(11f)
        isFakeBoldText = true
    }
    private val needCaptionPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF666666.toInt()
        textSize = sp(11f)
    }
    private val zeroPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF666666.toInt()
        textSize = sp(11f)
    }

    private val trackRect = RectF()
    private val intakeRect = RectF()
    private val burnRect = RectF()

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val w = MeasureSpec.getSize(widthMeasureSpec)
        val above = sp(14f).toInt()
        val track = dp(26f).toInt()
        val below = sp(16f).toInt()
        val h = above + track + below + paddingTop + paddingBottom
        setMeasuredDimension(w, resolveSize(h, heightMeasureSpec))
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val left = paddingLeft.toFloat()
        val right = (width - paddingRight).toFloat()
        val trackW = max(1f, right - left)
        val aboveH = sp(14f)
        val trackH = dp(26f)
        val trackTop = paddingTop + aboveH
        val trackBottom = trackTop + trackH
        val radius = dp(8f)

        trackRect.set(left, trackTop, right, trackBottom)
        canvas.drawRoundRect(trackRect, radius, radius, trackPaint)

        // Daily need ≈ half width; remaining half absorbs intake overflow.
        val halfScale = if (needKcal > 0f) needKcal * 2f else 0f
        val scale = max(halfScale, max(intakeKcal, max(burnKcal, 1f)))
        val intakeFrac = min(1f, intakeKcal / scale)
        val burnFrac = min(intakeFrac, burnKcal / scale)
        val burnLeftFrac = max(0f, intakeFrac - burnFrac)
        val needFrac = if (needKcal > 0f) min(1f, needKcal / scale) else 0.5f

        val intakeRight = left + trackW * intakeFrac
        intakeRect.set(left, trackTop, intakeRight, trackBottom)
        if (intakeFrac > 0f) {
            canvas.drawRoundRect(intakeRect, radius, radius, intakePaint)
        }

        val burnLeft = left + trackW * burnLeftFrac
        val burnRight = left + trackW * intakeFrac
        burnRect.set(burnLeft, trackTop, burnRight, trackBottom)
        if (burnFrac > 0f && burnRight > burnLeft) {
            canvas.drawRect(burnRect, burnPaint)
        }

        if (needKcal > 0f) {
            val nx = left + trackW * needFrac
            canvas.drawLine(nx, trackTop - dp(3f), nx, trackBottom + dp(3f), needMarkPaint)
            if (needCaption.isNotBlank()) {
                val tw = needCaptionPaint.measureText(needCaption)
                val cx = (nx - tw / 2f).coerceIn(left, right - tw)
                canvas.drawText(needCaption, cx, trackBottom + sp(13f), needCaptionPaint)
            }
        }

        canvas.drawText("0", left, trackBottom + sp(13f), zeroPaint)

        if (intakeLabel.isNotBlank() && intakeFrac > 0f) {
            val pad = dp(6f)
            val tw = labelPaint.measureText(intakeLabel)
            if (intakeRect.width() >= tw + pad * 2f) {
                canvas.drawText(
                    intakeLabel,
                    left + pad,
                    trackTop + trackH / 2f + labelPaint.textSize / 3f,
                    labelPaint,
                )
            }
        }

        if (burnLabel.isNotBlank() && burnFrac > 0f) {
            val pad = dp(4f)
            val tw = burnAbovePaint.measureText(burnLabel)
            val fits = burnRect.width() >= tw + pad * 2f
            if (fits) {
                val white = Paint(labelPaint).apply { color = 0xF2FFFFFF.toInt() }
                val cx = burnRect.centerX() - tw / 2f
                canvas.drawText(
                    burnLabel,
                    cx.coerceIn(burnRect.left + pad, burnRect.right - tw - pad),
                    trackTop + trackH / 2f + white.textSize / 3f,
                    white,
                )
            } else {
                val cx = (burnRect.centerX() - tw / 2f).coerceIn(left, right - tw)
                canvas.drawText(burnLabel, cx, paddingTop + sp(11f), burnAbovePaint)
            }
        }
    }

    fun bind(
        intake: Float,
        burn: Float?,
        need: Float?,
        intakeText: String,
        burnText: String,
        needText: String,
    ) {
        intakeKcal = intake
        burnKcal = burn ?: 0f
        needKcal = need ?: 0f
        intakeLabel = intakeText
        burnLabel = if ((burn ?: 0f) > 0f) burnText else ""
        needCaption = if ((need ?: 0f) > 0f) needText else ""
        requestLayout()
        invalidate()
    }

    private fun dp(v: Float): Float = v * resources.displayMetrics.density
    private fun sp(v: Float): Float = v * resources.displayMetrics.scaledDensity
}
