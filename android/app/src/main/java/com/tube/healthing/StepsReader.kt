package com.tube.healthing

import android.content.Context
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Build
import androidx.core.content.ContextCompat
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.time.TimeRangeFilter
import androidx.health.connect.client.aggregate.AggregateMetric
import java.time.LocalDate
import java.time.ZoneId
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/**
 * Teaching demo step reader for vivo / Android 14–16:
 * Health Connect (replaces Google Fit) → TYPE_STEP_COUNTER → manual.
 * Same kcal/step constant as the website (0.04). Not a medical/fitness prescription.
 */
class StepsReader(
    private val context: Context,
    private val prefs: SharedPreferences,
) {
    data class Reading(
        val steps: Int?,
        val source: String,
        val burnedKcal: Double? = null,
        val note: String = "",
    )

    fun healthConnectStatus(): String {
        return try {
            when (HealthConnectClient.getSdkStatus(context)) {
                HealthConnectClient.SDK_AVAILABLE -> "available"
                HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED -> "update_required"
                else -> "unavailable"
            }
        } catch (_: Throwable) {
            "unavailable"
        }
    }

    fun healthConnectClientOrNull(): HealthConnectClient? {
        return try {
            if (healthConnectStatus() != "available") null
            else HealthConnectClient.getOrCreate(context)
        } catch (_: Throwable) {
            null
        }
    }

    fun healthConnectPermissions(): Set<String> = setOf(
        HealthPermission.getReadPermission(StepsRecord::class),
        HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class),
    )

    suspend fun readHealthConnectToday(): Reading? {
        val client = healthConnectClientOrNull() ?: return null
        return try {
            val granted = client.permissionController.getGrantedPermissions()
            val stepsPerm = HealthPermission.getReadPermission(StepsRecord::class)
            if (!granted.contains(stepsPerm)) {
                return Reading(null, "android_health_connect", note = "permission_needed")
            }
            val zone = ZoneId.systemDefault()
            val start = LocalDate.now().atStartOfDay(zone).toInstant()
            val end = java.time.Instant.now()
            val caloriesPerm = HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class)
            val canReadCalories = granted.contains(caloriesPerm)
            val metrics = mutableSetOf<AggregateMetric<*>>(StepsRecord.COUNT_TOTAL)
            if (canReadCalories) {
                metrics.add(ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL)
            }
            val response = client.aggregate(
                AggregateRequest(
                    metrics = metrics,
                    timeRangeFilter = TimeRangeFilter.between(start, end),
                )
            )
            val total = response[StepsRecord.COUNT_TOTAL]?.toInt()
            val burnedValue = if (canReadCalories) {
                response[ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL]
                    ?.inKilocalories
                    ?.let { Math.round(it * 10.0) / 10.0 }
            } else null
            Reading(
                total,
                "android_health_connect",
                burnedKcal = burnedValue ?: total?.let { estimateBurned(it) },
            )
        } catch (e: Exception) {
            Reading(null, "android_health_connect", note = e.message ?: "error")
        }
    }

    fun hasActivityRecognition(): Boolean {
        if (Build.VERSION.SDK_INT < 29) return true
        return ContextCompat.checkSelfPermission(
            context,
            android.Manifest.permission.ACTIVITY_RECOGNITION
        ) == PackageManager.PERMISSION_GRANTED
    }

    /**
     * Blocking sensor read of today's steps via TYPE_STEP_COUNTER.
     * Uses last raw reading as day-start proxy when the calendar day rolls over
     * (undercounts overnight if the app was not opened near midnight).
     */
    fun readSensorToday(timeoutMs: Long = 2500L): Reading {
        if (!hasActivityRecognition()) {
            return Reading(null, "android_sensor", note = "permission_needed")
        }
        val sm = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        val sensor = sm.getDefaultSensor(Sensor.TYPE_STEP_COUNTER)
            ?: return Reading(null, "android_sensor", note = "no_sensor")

        val latch = CountDownLatch(1)
        val counter = AtomicInteger(-1)
        val listener = object : SensorEventListener {
            override fun onSensorChanged(event: SensorEvent?) {
                if (event == null || event.sensor.type != Sensor.TYPE_STEP_COUNTER) return
                counter.set(event.values[0].toInt())
                latch.countDown()
            }

            override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
        }
        sm.registerListener(listener, sensor, SensorManager.SENSOR_DELAY_NORMAL)
        try {
            latch.await(timeoutMs, TimeUnit.MILLISECONDS)
        } finally {
            sm.unregisterListener(listener)
        }
        val raw = counter.get()
        if (raw < 0) return Reading(null, "android_sensor", note = "no_reading")

        val today = LocalDate.now().toString()
        val storedDate = prefs.getString(PREF_BASELINE_DATE, null)
        var baseline = prefs.getInt(PREF_BASELINE, -1)
        val lastRaw = prefs.getInt(PREF_LAST_RAW, -1)

        when {
            // Counter reset after reboot.
            baseline >= 0 && raw < baseline -> baseline = 0
            lastRaw >= 0 && raw < lastRaw -> baseline = 0
            // New calendar day: approximate midnight with last raw (keeps overnight walk).
            storedDate != null && storedDate != today && lastRaw >= 0 -> baseline = lastRaw
            storedDate != today || baseline < 0 -> baseline = raw
        }

        prefs.edit()
            .putString(PREF_BASELINE_DATE, today)
            .putInt(PREF_BASELINE, baseline)
            .putInt(PREF_LAST_RAW, raw)
            .apply()

        val steps = (raw - baseline).coerceAtLeast(0)
        return Reading(steps, "android_sensor", burnedKcal = estimateBurned(steps))
    }

    companion object {
        const val KCAL_PER_STEP = 0.04
        private const val PREF_BASELINE = "step_counter_baseline"
        private const val PREF_BASELINE_DATE = "step_counter_baseline_date"
        private const val PREF_LAST_RAW = "step_counter_last_raw"

        fun estimateBurned(steps: Int): Double =
            Math.round(steps * KCAL_PER_STEP * 10.0) / 10.0
    }
}
