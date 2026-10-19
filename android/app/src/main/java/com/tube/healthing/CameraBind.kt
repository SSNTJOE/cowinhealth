package com.tube.healthing

import android.os.Build
import android.util.Size
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.UseCase
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.lifecycle.LifecycleOwner

object CameraBind {
    fun isEmulator(): Boolean {
        val fingerprint = Build.FINGERPRINT.lowercase()
        val model = Build.MODEL.lowercase()
        val hardware = Build.HARDWARE.lowercase()
        return fingerprint.contains("generic") ||
            fingerprint.contains("emulator") ||
            model.contains("sdk_gphone") ||
            model.contains("emulator") ||
            hardware.contains("ranchu") ||
            hardware.contains("goldfish")
    }

    fun resolution(): ResolutionSelector {
        val size = if (isEmulator()) Size(640, 480) else Size(1280, 720)
        return ResolutionSelector.Builder()
            .setResolutionStrategy(
                ResolutionStrategy(
                    size,
                    ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER
                )
            )
            .build()
    }

    fun bind(
        owner: LifecycleOwner,
        provider: ProcessCameraProvider,
        preferred: CameraSelector,
        vararg useCases: UseCase
    ): Camera? {
        val order = linkedSetOf(preferred, CameraSelector.DEFAULT_BACK_CAMERA, CameraSelector.DEFAULT_FRONT_CAMERA)
        for (selector in order) {
            if (!provider.hasCamera(selector)) continue
            try {
                provider.unbindAll()
                return provider.bindToLifecycle(owner, selector, *useCases)
            } catch (_: Exception) {
            }
        }
        return null
    }
}
