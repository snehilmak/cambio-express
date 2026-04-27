package com.dinerobook.tv

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity

/**
 * Headless router. Decides on launch whether to send the operator
 * to [PairingActivity] (no stored URL yet) or [DisplayActivity]
 * (already paired). Has no UI of its own — finishes immediately
 * after firing the right intent so the back stack stays clean.
 *
 * When the WebView in DisplayActivity hits a 404 (revoked / addon
 * off / token rotated), it wipes Prefs and re-launches MainActivity,
 * which routes the operator back to pairing automatically.
 */
class MainActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefs = Prefs(this)
        val nextScreen = if (prefs.displayUrl.isNullOrEmpty()) {
            PairingActivity::class.java
        } else {
            DisplayActivity::class.java
        }
        startActivity(Intent(this, nextScreen))
        finish()
    }
}
