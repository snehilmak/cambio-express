package com.dinerobook.tv

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import com.dinerobook.tv.databinding.ActivityDisplayBinding

/**
 * Fullscreen WebView pointing at the per-device URL the operator
 * paired with. The page itself (templates/tv_display_public.html
 * on the backend) auto-refreshes every 30 seconds via fetch +
 * meta-tag comparison, so the app doesn't need its own polling.
 *
 * Lockdown:
 *   - No address bar, no chrome — the WebView IS the screen.
 *   - Fullscreen + immersive sticky → status bar / nav bar hidden.
 *   - JavaScript ENABLED (the auto-refresh poll relies on fetch).
 *   - File access / DOM storage / cookies all OFF — there's nothing
 *     for the page to persist client-side, and locking it down means
 *     a compromised page can't squat on the WebView profile.
 *   - Cleartext (http://) explicitly rejected; backend is HTTPS-only.
 *
 * Fallback:
 *   - When the WebView hits a 404 (revoked / addon off / TVPairing
 *     superseded by a fresh redeem), we wipe Prefs and bounce back
 *     to MainActivity, which routes to PairingActivity. The
 *     operator never sees a raw "404 Not Found" page.
 *
 * Re-pair shortcut:
 *   - Long-press MENU on the Fire TV remote (KEYCODE_MENU) clears
 *     state and re-opens pairing. Useful for unpair-and-rebind
 *     without uninstalling.
 */
class DisplayActivity : AppCompatActivity() {

    private lateinit var binding: ActivityDisplayBinding
    private lateinit var prefs: Prefs

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityDisplayBinding.inflate(layoutInflater)
        setContentView(binding.root)

        prefs = Prefs(this)
        val url = prefs.displayUrl
        if (url.isNullOrEmpty()) {
            // Belt and suspenders — MainActivity should have routed
            // to pairing already, but guard in case the prefs were
            // wiped between MainActivity finishing and us starting.
            backToPairing()
            return
        }

        // Keep the screen on — store wants the rates visible all day.
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        // Match the page's near-black background so the half-second
        // before WebView paints isn't a white flash.
        binding.root.setBackgroundColor(Color.BLACK)
        binding.webview.setBackgroundColor(Color.BLACK)

        configureWebView(binding.webview)
        binding.webview.loadUrl(url)
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configureWebView(web: WebView) {
        web.settings.apply {
            javaScriptEnabled = true        // auto-refresh poll uses fetch()
            domStorageEnabled = false       // nothing to persist client-side
            allowFileAccess = false
            allowContentAccess = false
            cacheMode = android.webkit.WebSettings.LOAD_NO_CACHE
            mediaPlaybackRequiresUserGesture = false
            mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
        }
        web.webViewClient = object : WebViewClient() {

            // Reject any navigation outside the paired host. The page
            // never tries to navigate, but a compromised CSS/JS asset
            // could; this is belt-and-suspenders.
            override fun shouldOverrideUrlLoading(
                view: WebView, request: WebResourceRequest,
            ): Boolean {
                val target = request.url.toString()
                val ours = prefs.displayUrl ?: return true
                val ourHost = android.net.Uri.parse(ours).host ?: return true
                return request.url.host != ourHost
            }

            // The crucial bit: a 404 from the per-device URL means
            // the pairing was revoked (a fresh pair-code redeem
            // superseded us, or the addon was switched off). Wipe
            // local state and route back to pairing.
            override fun onReceivedHttpError(
                view: WebView, request: WebResourceRequest,
                errorResponse: WebResourceResponse,
            ) {
                if (request.isForMainFrame && errorResponse.statusCode == 404) {
                    prefs.clear()
                    backToPairing()
                }
            }
        }
    }

    private fun backToPairing() {
        startActivity(
            Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK)
        )
        finish()
    }

    // Long-press MENU resets the device — operator can re-pair
    // without uninstalling.
    override fun onKeyLongPress(keyCode: Int, event: KeyEvent): Boolean {
        if (keyCode == KeyEvent.KEYCODE_MENU) {
            prefs.clear()
            backToPairing()
            return true
        }
        return super.onKeyLongPress(keyCode, event)
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideSystemBars()
    }

    @Suppress("DEPRECATION")
    private fun hideSystemBars() {
        // Sticky immersive on Lollipop and above. We use the
        // deprecated systemUiVisibility flags rather than the newer
        // WindowInsetsController only because minSdk is 22 and
        // WindowInsetsController is API 30+; the older flags work
        // on every Fire TV in the install base.
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_FULLSCREEN
                or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        )
    }

    override fun onDestroy() {
        binding.webview.stopLoading()
        binding.webview.destroy()
        super.onDestroy()
    }
}
