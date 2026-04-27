package com.dinerobook.tv

import android.content.Context
import android.content.SharedPreferences

/**
 * Tiny SharedPreferences wrapper for the only state the app cares
 * about: the device-bound URL the operator paired with.
 *
 * Storage philosophy: we keep ONLY [displayUrl] (the per-device URL
 * returned by /api/tv-pair/redeem), not the device_token in
 * isolation. The token is embedded in the URL anyway, and storing
 * the URL means the WebView can boot with a single read.
 *
 * "Re-pair" wipes everything so the operator can rebind the device
 * to a different store / display from inside the app without
 * reinstalling.
 */
class Prefs(context: Context) {
    private val sp: SharedPreferences =
        context.applicationContext.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    var displayUrl: String?
        get() = sp.getString(KEY_URL, null)
        set(value) {
            sp.edit().apply {
                if (value.isNullOrEmpty()) remove(KEY_URL) else putString(KEY_URL, value)
                apply()
            }
        }

    fun clear() {
        sp.edit().clear().apply()
    }

    companion object {
        private const val FILE = "dinerobook_tv_prefs"
        private const val KEY_URL = "display_url"
    }
}
