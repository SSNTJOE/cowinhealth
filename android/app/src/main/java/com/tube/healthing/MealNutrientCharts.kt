package com.tube.healthing

import android.graphics.Color
import com.github.mikephil.charting.charts.BarChart
import com.github.mikephil.charting.charts.CombinedChart
import com.github.mikephil.charting.charts.ScatterChart
import com.github.mikephil.charting.components.Legend
import com.github.mikephil.charting.components.LimitLine
import com.github.mikephil.charting.components.XAxis
import com.github.mikephil.charting.components.YAxis
import com.github.mikephil.charting.data.BarData
import com.github.mikephil.charting.data.BarDataSet
import com.github.mikephil.charting.data.BarEntry
import com.github.mikephil.charting.data.CombinedData
import com.github.mikephil.charting.data.Entry
import com.github.mikephil.charting.data.LineData
import com.github.mikephil.charting.data.LineDataSet
import com.github.mikephil.charting.data.ScatterData
import com.github.mikephil.charting.data.ScatterDataSet
import com.github.mikephil.charting.formatter.IndexAxisValueFormatter
import com.github.mikephil.charting.formatter.ValueFormatter
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.max

/**
 * Mirrors website meal charts in app.js:
 * - grouped bar: intake % vs 100% target
 * - multi-series trend: surplus/target % over days with meals (0 = on target)
 */
object MealNutrientCharts {
    private val TREND_COLORS = intArrayOf(
        Color.parseColor("#2a6f97"), Color.parseColor("#c45a3c"), Color.parseColor("#2e8b57"),
        Color.parseColor("#8b5a2b"), Color.parseColor("#6a5acd"), Color.parseColor("#d2691e"),
        Color.parseColor("#20b2aa"), Color.parseColor("#b22222"), Color.parseColor("#708090"),
        Color.parseColor("#daa520"), Color.parseColor("#4169e1"), Color.parseColor("#cd5c5c"),
        Color.parseColor("#556b2f"), Color.parseColor("#9932cc"),
    )

    fun bindIntakeBar(
        chart: BarChart,
        day: JSONObject?,
        emptyText: String,
        intakeLabel: String,
        targetLabel: String,
    ) {
        chart.description.isEnabled = false
        chart.setDrawGridBackground(false)
        chart.axisRight.isEnabled = false
        chart.setFitBars(true)
        chart.setNoDataText(emptyText)
        chart.setScaleEnabled(false)
        chart.setPinchZoom(false)
        chart.legend.verticalAlignment = Legend.LegendVerticalAlignment.BOTTOM
        chart.legend.horizontalAlignment = Legend.LegendHorizontalAlignment.CENTER
        chart.legend.orientation = Legend.LegendOrientation.HORIZONTAL
        chart.legend.setDrawInside(false)
        chart.legend.isWordWrapEnabled = true
        chart.setDrawValueAboveBar(true)

        val keys = day?.optJSONArray("nutrient_keys")
        val labelsArr = day?.optJSONArray("chart_labels")
        val totals = day?.optJSONObject("totals")
        val targets = day?.optJSONObject("targets")
        if (keys == null || keys.length() == 0 || targets == null) {
            chart.clear()
            chart.invalidate()
            return
        }

        val labels = ArrayList<String>()
        val intakeEntries = ArrayList<BarEntry>()
        val targetEntries = ArrayList<BarEntry>()
        var maxPct = 100f
        var x = 0
        for (i in 0 until keys.length()) {
            val key = keys.optString(i)
            val target = targets.optDouble(key, 0.0)
            if (!(target > 0)) continue
            val total = totals?.optDouble(key, 0.0) ?: 0.0
            val intakePct = ((1000.0 * total) / target).toFloat() / 10f
            labels.add(labelsArr?.optString(i)?.ifBlank { shortLabel(key) } ?: shortLabel(key))
            intakeEntries.add(BarEntry(x.toFloat(), intakePct))
            targetEntries.add(BarEntry(x.toFloat(), 100f))
            maxPct = max(maxPct, intakePct)
            x++
        }
        if (labels.isEmpty()) {
            chart.clear()
            chart.invalidate()
            return
        }

        val intakeSet = BarDataSet(intakeEntries, intakeLabel).apply {
            color = Color.argb(166, 42, 111, 151)
            setDrawValues(true)
            valueTextSize = 9f
            valueFormatter = PctFormatter()
        }
        val targetSet = BarDataSet(targetEntries, targetLabel).apply {
            color = Color.argb(90, 120, 120, 120)
            setDrawValues(false)
        }
        val groupSpace = 0.2f
        val barSpace = 0.05f
        val barWidth = 0.35f
        chart.data = BarData(intakeSet, targetSet).apply {
            this.barWidth = barWidth
            groupBars(0f, groupSpace, barSpace)
        }
        chart.xAxis.apply {
            position = XAxis.XAxisPosition.BOTTOM
            setDrawGridLines(false)
            granularity = 1f
            labelCount = labels.size
            valueFormatter = IndexAxisValueFormatter(labels)
            labelRotationAngle = -35f
            textSize = 9f
            axisMinimum = 0f
            axisMaximum = labels.size.toFloat()
            setCenterAxisLabels(true)
        }
        chart.axisLeft.apply {
            axisMinimum = 0f
            axisMaximum = max(maxPct * 1.15f, 110f)
            granularity = 20f
            valueFormatter = PctFormatter()
            setDrawGridLines(true)
        }
        chart.invalidate()
    }

    fun bindSurplusTrend(
        chart: CombinedChart,
        month: JSONObject?,
        dayFallback: JSONObject?,
        emptyText: String,
    ) {
        chart.description.isEnabled = false
        chart.setDrawGridBackground(false)
        chart.axisRight.isEnabled = false
        chart.setNoDataText(emptyText)
        chart.setScaleEnabled(true)
        chart.setPinchZoom(false)
        chart.legend.verticalAlignment = Legend.LegendVerticalAlignment.BOTTOM
        chart.legend.horizontalAlignment = Legend.LegendHorizontalAlignment.CENTER
        chart.legend.orientation = Legend.LegendOrientation.HORIZONTAL
        chart.legend.setDrawInside(false)
        chart.legend.isWordWrapEnabled = true
        chart.legend.form = Legend.LegendForm.CIRCLE
        chart.drawOrder = arrayOf(
            CombinedChart.DrawOrder.LINE,
            CombinedChart.DrawOrder.SCATTER,
        )

        val keys = month?.optJSONArray("nutrient_keys")
            ?: dayFallback?.optJSONArray("nutrient_keys")
        val labelsArr = month?.optJSONArray("chart_labels")
            ?: dayFallback?.optJSONArray("chart_labels")
        val targets = month?.optJSONObject("targets")
            ?: dayFallback?.optJSONObject("targets")
        val days = month?.optJSONArray("days")
        if (keys == null || keys.length() == 0 || targets == null || days == null) {
            chart.clear()
            chart.invalidate()
            return
        }

        val daysWithMeals = ArrayList<JSONObject>()
        for (i in 0 until days.length()) {
            val d = days.optJSONObject(i) ?: continue
            if (d.optBoolean("has_meals", false)) daysWithMeals.add(d)
        }
        if (daysWithMeals.isEmpty()) {
            chart.clear()
            chart.invalidate()
            return
        }

        val xLabels = daysWithMeals.map { day ->
            val iso = day.optString("date")
            if (iso.length >= 10) "${iso.substring(5, 7)}/${iso.substring(8, 10)}" else iso
        }

        val lineData = LineData()
        val scatterData = ScatterData()
        var maxAbs = 0f
        var seriesIndex = 0
        for (i in 0 until keys.length()) {
            val key = keys.optString(i)
            val target = targets.optDouble(key, 0.0)
            if (!(target > 0)) continue
            val color = TREND_COLORS[seriesIndex % TREND_COLORS.size]
            val label = labelsArr?.optString(i)?.ifBlank { shortLabel(key) } ?: shortLabel(key)
            val lineEntries = ArrayList<Entry>()
            val scatterEntries = ArrayList<Entry>()
            for (dIdx in daysWithMeals.indices) {
                val day = daysWithMeals[dIdx]
                val surplusObj = day.optJSONObject("surplus")
                val totals = day.optJSONObject("totals")
                val delta = when {
                    surplusObj != null && !surplusObj.isNull(key) -> surplusObj.optDouble(key, 0.0)
                    else -> (totals?.optDouble(key, 0.0) ?: 0.0) - target
                }
                val pct = ((1000.0 * delta) / target).toFloat() / 10f
                if (pct.isFinite()) maxAbs = max(maxAbs, abs(pct))
                lineEntries.add(Entry(dIdx.toFloat(), pct))
                scatterEntries.add(Entry(dIdx.toFloat(), pct))
            }
            lineData.addDataSet(
                LineDataSet(lineEntries, "").apply {
                    this.color = color
                    lineWidth = 2f
                    setDrawCircles(false)
                    setDrawValues(false)
                    setDrawHighlightIndicators(false)
                    mode = LineDataSet.Mode.CUBIC_BEZIER
                    cubicIntensity = 0.12f
                    form = Legend.LegendForm.NONE
                    axisDependency = YAxis.AxisDependency.LEFT
                    isHighlightEnabled = false
                }
            )
            scatterData.addDataSet(
                ScatterDataSet(scatterEntries, label).apply {
                    this.color = color
                    scatterShapeSize = 12f
                    setDrawValues(false)
                    axisDependency = YAxis.AxisDependency.LEFT
                    setScatterShape(scatterShapeFor(seriesIndex))
                }
            )
            seriesIndex++
        }
        if (seriesIndex == 0) {
            chart.clear()
            chart.invalidate()
            return
        }

        val axisBound = max(20f, ceil(maxAbs / 10f) * 10f)
        chart.xAxis.apply {
            position = XAxis.XAxisPosition.BOTTOM
            granularity = 1f
            valueFormatter = IndexAxisValueFormatter(xLabels)
            setDrawGridLines(false)
            labelRotationAngle = -20f
            textSize = 10f
        }
        chart.axisLeft.apply {
            removeAllLimitLines()
            axisMinimum = -axisBound
            axisMaximum = axisBound
            valueFormatter = PctFormatter(signed = true)
            setDrawGridLines(true)
            addLimitLine(
                LimitLine(0f, "").apply {
                    lineWidth = 2f
                    lineColor = Color.BLACK
                    enableDashedLine(0f, 0f, 0f)
                }
            )
        }
        chart.data = CombinedData().apply {
            setData(lineData)
            setData(scatterData)
        }
        chart.invalidate()
    }

    private fun scatterShapeFor(index: Int): ScatterChart.ScatterShape {
        val shapes = arrayOf(
            ScatterChart.ScatterShape.CIRCLE,
            ScatterChart.ScatterShape.TRIANGLE,
            ScatterChart.ScatterShape.SQUARE,
            ScatterChart.ScatterShape.CROSS,
            ScatterChart.ScatterShape.X,
            ScatterChart.ScatterShape.CIRCLE,
            ScatterChart.ScatterShape.TRIANGLE,
            ScatterChart.ScatterShape.SQUARE,
        )
        return shapes[index % shapes.size]
    }

    private fun shortLabel(key: String): String =
        key.replace(Regex("[（(][^）)]*[）)]"), "").trim().ifBlank { key }

    private class PctFormatter(private val signed: Boolean = false) : ValueFormatter() {
        override fun getFormattedValue(value: Float): String {
            val rounded = (Math.round(value * 10f) / 10f)
            val body = if (rounded == rounded.toInt().toFloat()) {
                "${rounded.toInt()}%"
            } else {
                "${rounded}%"
            }
            return if (signed && rounded > 0) "+$body" else body
        }
    }

    /** Optional helper if callers pass JSONArray keys from day payload. */
    @Suppress("unused")
    fun keyList(keys: JSONArray?): List<String> {
        if (keys == null) return emptyList()
        return (0 until keys.length()).map { keys.optString(it) }
    }
}
