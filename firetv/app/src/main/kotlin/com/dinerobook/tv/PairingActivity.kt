package com.dinerobook.tv

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.dinerobook.tv.databinding.ActivityPairingBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Pairing screen — TV-initiated flow.
 *
 * On launch:
 *   1. POST /api/tv-pair/init → server returns {code, device_token, ttl}.
 *   2. Display the 6-character code BIG and centered. Show a line
 *      below telling the operator where to enter it ("Open
 *      dinerobook.com/tv-display in your account, then type this
 *      code"). Show a smaller TTL countdown.
 *   3. Poll GET /api/tv-pair/status every 2 seconds with the
 *      device_token. When the response flips to "claimed", stash
 *      the display_url in Prefs and hand off to DisplayActivity.
 *      When "expired", silently re-init (fresh code, fresh poll).
 *
 * No UI input on this screen. Fire TV remote can't reasonably type
 * 6 chars in 15 seconds; the operator types into a real keyboard
 * on the admin side. This activity just narrates state.
 */
class PairingActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPairingBinding
    private lateinit var prefs: Prefs
    private lateinit var api: PairApi

    /** The token from /init; empty until the first init succeeds. */
    private var deviceToken: String = ""

    /** Cancelable poll loop — stopped on transitions / activity death. */
    private var pollJob: Job? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPairingBinding.inflate(layoutInflater)
        setContentView(binding.root)

        prefs = Prefs(this)
        api   = PairApi(BuildConfig.BASE_URL)

        binding.tvBaseUrl.text = getString(
            R.string.pair_where_to_enter, BuildConfig.BASE_URL,
        )

        // Kick off the init → poll loop.
        startPairingFlow()
    }

    private fun startPairingFlow() {
        showLoading()
        lifecycleScope.launch {
            // 1. Get a code + token.
            val label = "Fire TV — ${Build.MODEL}".take(80)
            val initResult = withContext(Dispatchers.IO) { api.init(label) }
            when (initResult) {
                is PairApi.InitResult.Success -> {
                    deviceToken = initResult.deviceToken
                    showCode(initResult.code)
                    startPolling()
                }
                is PairApi.InitResult.Error -> {
                    showError(getString(R.string.pair_error_init, initResult.message))
                }
            }
        }
    }

    private fun startPolling() {
        pollJob?.cancel()
        pollJob = lifecycleScope.launch {
            while (isActive) {
                delay(POLL_INTERVAL_MS)
                val result = withContext(Dispatchers.IO) {
                    api.pollStatus(deviceToken)
                }
                when (result) {
                    is PairApi.StatusResult.Claimed -> {
                        prefs.displayUrl = result.displayUrl
                        startActivity(Intent(this@PairingActivity, DisplayActivity::class.java))
                        finish()
                        return@launch
                    }
                    is PairApi.StatusResult.Pending -> {
                        // Still waiting. Refresh the displayed code in case
                        // the server's view of "the current code" diverged
                        // (e.g. activity re-created mid-flow).
                        if (result.code.isNotEmpty()) showCode(result.code)
                    }
                    is PairApi.StatusResult.Expired -> {
                        // Code aged out — silently get a fresh one and
                        // restart the poll loop.
                        startPairingFlow()
                        return@launch
                    }
                    is PairApi.StatusResult.Error -> {
                        // Treat poll-time errors as transient — keep
                        // looping. The UI doesn't change; if the network
                        // is down for real, the operator will see the
                        // code stuck for a while.
                    }
                }
            }
        }
    }

    private fun showLoading() {
        binding.tvCode.text = "------"
        binding.tvCode.alpha = 0.4f
        binding.tvError.visibility = View.GONE
    }

    private fun showCode(code: String) {
        // "ABC234" → "ABC 234" — easier to read across a counter.
        val pretty = if (code.length == 6) "${code.substring(0, 3)} ${code.substring(3)}" else code
        binding.tvCode.text = pretty
        binding.tvCode.alpha = 1.0f
        binding.tvError.visibility = View.GONE
    }

    private fun showError(msg: String) {
        binding.tvCode.text = "------"
        binding.tvCode.alpha = 0.3f
        binding.tvError.text = msg
        binding.tvError.visibility = View.VISIBLE
        // Retry init after a longer delay — usually a transient
        // network blip.
        lifecycleScope.launch {
            delay(RETRY_DELAY_MS)
            if (isFinishing.not()) startPairingFlow()
        }
    }

    override fun onDestroy() {
        pollJob?.cancel()
        super.onDestroy()
    }

    companion object {
        // Aggressive enough that the TV transitions within 2-3
        // seconds of the operator clicking Pair, gentle enough
        // that a paired-and-forgotten store doesn't hammer the
        // backend.
        private const val POLL_INTERVAL_MS = 2_000L
        // Backoff after a failed /init.
        private const val RETRY_DELAY_MS  = 5_000L
    }
}
