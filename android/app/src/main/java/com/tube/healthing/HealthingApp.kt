package com.tube.healthing

import android.app.Application

class HealthingApp : Application() {
    override fun onCreate() {
        super.onCreate()
        AppLocale.bootstrap(this)
    }
}
