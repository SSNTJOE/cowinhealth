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

    fun trySizes(): List<Size> {
        return if (isEmulator()) {
            listOf(Size(640, 480))
        } else {
            listOf(Size(1280, 720), Size(640, 480))
        }
    }

    fun resolution(size: Size = trySizes().first()): ResolutionSelector {
        return ResolutionSelector.Builder()
            .setResolutionStrategy(
                ResolutionStrategy(
                    size,
                    ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER
                )
            )
            .build()
    }

    fun bindFacing(
        owner: LifecycleOwner,
        provider: ProcessCameraProvider,
        facing: CameraSelector,
        vararg useCases: UseCase
    ): Camera? {
        if (!provider.hasCamera(facing)) return null
        return try {
            provider.unbindAll()
            provider.bindToLifecycle(owner, facing, *useCases)
        } catch (_: Exception) {
            null
        }
    }

    /** Face / tongue: front camera only. Do not fall back to the rear lens. */
    fun bindFrontOnly(
        owner: LifecycleOwner,
        provider: ProcessCameraProvider,
        vararg useCases: UseCase
    ): Camera? = bindFacing(owner, provider, CameraSelector.DEFAULT_FRONT_CAMERA, *useCases)

    /** Pulse / PPG: rear camera only. Never silently switch to the selfie lens. */
    fun bindRearOnly(
        owner: LifecycleOwner,
        provider: ProcessCameraProvider,
        vararg useCases: UseCase
    ): Camera? = bindFacing(owner, provider, CameraSelector.DEFAULT_BACK_CAMERA, *useCases)
}
