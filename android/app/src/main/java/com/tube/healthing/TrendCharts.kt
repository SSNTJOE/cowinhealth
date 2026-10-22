package com.tube.healthing

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import com.github.mikephil.charting.charts.CombinedChart
import com.github.mikephil.charting.charts.ScatterChart
import com.github.mikephil.charting.components.Legend
import com.github.mikephil.charting.components.XAxis
import com.github.mikephil.charting.components.YAxis
import com.github.mikephil.charting.data.CombinedData
import com.github.mikephil.charting.data.Entry
import com.github.mikephil.charting.data.LineData
import com.github.mikephil.charting.data.LineDataSet
import com.github.mikephil.charting.data.ScatterData
import com.github.mikephil.charting.data.ScatterDataSet
import com.github.mikephil.charting.formatter.IndexAxisValueFormatter
import com.github.mikephil.charting.interfaces.datasets.IScatterDataSet
import com.github.mikephil.charting.renderer.scatter.IShapeRenderer
import com.github.mikephil.charting.utils.ViewPortHandler
import org.json.JSONObject

object TrendCharts {
    fun bind(chart: CombinedChart, trend: JSONObject?) {
        chart.description.isEnabled = false
        chart.setDrawGridBackground(false)
        chart.axisRight.isEnabled = false
        chart.legend.verticalAlignment = Legend.LegendVerticalAlignment.BOTTOM
        chart.legend.horizontalAlignment = Legend.LegendHorizontalAlignment.CENTER
        chart.legend.orientation = Legend.LegendOrientation.HORIZONTAL
        chart.legend.setDrawInside(false)
        chart.legend.isWordWrapEnabled = true
        chart.legend.form = Legend.LegendForm.CIRCLE
        chart.setNoDataText("尚無足夠紀錄可畫趨勢")
        chart.drawOrder = arrayOf(
            CombinedChart.DrawOrder.LINE,
            CombinedChart.DrawOrder.SCATTER,
        )
        val organs = trend?.optJSONArray("organs")
        if (organs == null || organs.length() == 0) {
            chart.clear()
            chart.invalidate()
            return
        }
        val labels = mutableListOf<String>()
        val first = organs.optJSONObject(0)
        val firstPoints = first?.optJSONArray("points")
        if (firstPoints != null) {
            for (i in 0 until firstPoints.length()) {
                val t = firstPoints.optJSONObject(i)?.optString("t").orEmpty()
                labels.add(t.replace("T", " ").take(16))
            }
        }
        if (labels.isEmpty()) {
            chart.clear()
            chart.invalidate()
            return
        }
        val lineData = LineData()
        val scatterData = ScatterData()
        for (i in 0 until organs.length()) {
            val organ = organs.optJSONObject(i) ?: continue
            val color = Color.parseColor(organ.optString("color", "#888888"))
            val points = organ.optJSONArray("points") ?: continue
            val lineEntries = ArrayList<Entry>()
            val scatterEntries = ArrayList<Entry>()
            for (p in 0 until points.length()) {
                val pt = points.optJSONObject(p) ?: continue
                val y = pt.optDouble("y", 5.0).toFloat()
                lineEntries.add(Entry(p.toFloat(), y))
                scatterEntries.add(Entry(p.toFloat(), y))
            }
            val label = organ.optString("label")
            val line = LineDataSet(lineEntries, "").apply {
                this.color = color
                lineWidth = 2f
                setDrawCircles(false)
                setDrawValues(false)
                setDrawHighlightIndicators(false)
                form = Legend.LegendForm.NONE
                axisDependency = YAxis.AxisDependency.LEFT
            }
            val scatter = ScatterDataSet(scatterEntries, label).apply {
                this.color = color
                scatterShapeSize = 14f
                setDrawValues(false)
                axisDependency = YAxis.AxisDependency.LEFT
                applyMarker(this, organ.optString("marker"))
            }
            lineData.addDataSet(line)
            scatterData.addDataSet(scatter)
        }
        // Avoid duplicate legend entries from lines + markers.
        for (set in lineData.dataSets) set.isHighlightEnabled = false
        lineData.setDrawValues(false)

        val xAxis = chart.xAxis
        xAxis.position = XAxis.XAxisPosition.BOTTOM
        xAxis.granularity = 1f
        xAxis.valueFormatter = IndexAxisValueFormatter(labels)
        xAxis.labelRotationAngle = -35f
        xAxis.setDrawGridLines(false)

        val y = chart.axisLeft
        y.axisMinimum = (trend?.optInt("y_min", 1) ?: 1).toFloat()
        y.axisMaximum = (trend?.optInt("y_max", 10) ?: 10).toFloat()
        y.granularity = 1f
        y.setLabelCount(10, true)

        chart.data = CombinedData().apply {
            setData(lineData)
            setData(scatterData)
        }
        chart.invalidate()
    }

    private fun applyMarker(set: ScatterDataSet, marker: String) {
        when (marker) {
            "circle" -> set.setScatterShape(ScatterChart.ScatterShape.CIRCLE)
            "triangle" -> set.setScatterShape(ScatterChart.ScatterShape.TRIANGLE)
            "square" -> set.setScatterShape(ScatterChart.ScatterShape.SQUARE)
            "x" -> set.setScatterShape(ScatterChart.ScatterShape.X)
            "plus" -> set.setScatterShape(ScatterChart.ScatterShape.CROSS)
            "diamond" -> {
                set.setScatterShape(ScatterChart.ScatterShape.SQUARE)
                set.shapeRenderer = DiamondRenderer()
            }
            "star" -> {
                set.setScatterShape(ScatterChart.ScatterShape.SQUARE)
                set.shapeRenderer = StarRenderer()
            }
            "rounded" -> {
                set.setScatterShape(ScatterChart.ScatterShape.SQUARE)
                set.shapeRenderer = RoundedRenderer()
            }
            "dash" -> {
                set.setScatterShape(ScatterChart.ScatterShape.SQUARE)
                set.shapeRenderer = DashRenderer()
            }
            "line" -> {
                set.setScatterShape(ScatterChart.ScatterShape.SQUARE)
                set.shapeRenderer = TickRenderer()
            }
            else -> set.setScatterShape(ScatterChart.ScatterShape.CIRCLE)
        }
    }
}

private class DiamondRenderer : IShapeRenderer {
    override fun renderShape(
        c: Canvas, dataSet: IScatterDataSet, viewPortHandler: ViewPortHandler,
        posX: Float, posY: Float, renderPaint: Paint
    ) {
        val s = dataSet.scatterShapeSize / 2f
        val path = Path()
        path.moveTo(posX, posY - s)
        path.lineTo(posX + s, posY)
        path.lineTo(posX, posY + s)
        path.lineTo(posX - s, posY)
        path.close()
        c.drawPath(path, renderPaint)
    }
}

private class StarRenderer : IShapeRenderer {
    override fun renderShape(
        c: Canvas, dataSet: IScatterDataSet, viewPortHandler: ViewPortHandler,
        posX: Float, posY: Float, renderPaint: Paint
    ) {
        val r = dataSet.scatterShapeSize / 2f
        val path = Path()
        for (i in 0 until 5) {
            val a = Math.toRadians(-90.0 + i * 72.0)
            val x = posX + r * Math.cos(a).toFloat()
            val y = posY + r * Math.sin(a).toFloat()
            if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
            val b = Math.toRadians(-90.0 + i * 72.0 + 36.0)
            path.lineTo(posX + r * 0.45f * Math.cos(b).toFloat(), posY + r * 0.45f * Math.sin(b).toFloat())
        }
        path.close()
        c.drawPath(path, renderPaint)
    }
}

private class RoundedRenderer : IShapeRenderer {
    override fun renderShape(
        c: Canvas, dataSet: IScatterDataSet, viewPortHandler: ViewPortHandler,
        posX: Float, posY: Float, renderPaint: Paint
    ) {
        val s = dataSet.scatterShapeSize / 2f
        c.drawRoundRect(RectF(posX - s, posY - s, posX + s, posY + s), s * 0.45f, s * 0.45f, renderPaint)
    }
}

private class DashRenderer : IShapeRenderer {
    override fun renderShape(
        c: Canvas, dataSet: IScatterDataSet, viewPortHandler: ViewPortHandler,
        posX: Float, posY: Float, renderPaint: Paint
    ) {
        val s = dataSet.scatterShapeSize / 2f
        val oldStyle = renderPaint.style
        val oldWidth = renderPaint.strokeWidth
        renderPaint.strokeWidth = 4f
        renderPaint.style = Paint.Style.STROKE
        c.drawLine(posX - s, posY, posX + s, posY, renderPaint)
        renderPaint.style = oldStyle
        renderPaint.strokeWidth = oldWidth
    }
}

private class TickRenderer : IShapeRenderer {
    override fun renderShape(
        c: Canvas, dataSet: IScatterDataSet, viewPortHandler: ViewPortHandler,
        posX: Float, posY: Float, renderPaint: Paint
    ) {
        val s = dataSet.scatterShapeSize / 2f
        val oldStyle = renderPaint.style
        val oldWidth = renderPaint.strokeWidth
        renderPaint.strokeWidth = 4f
        renderPaint.style = Paint.Style.STROKE
        c.drawLine(posX, posY - s, posX, posY + s, renderPaint)
        renderPaint.style = oldStyle
        renderPaint.strokeWidth = oldWidth
    }
}
