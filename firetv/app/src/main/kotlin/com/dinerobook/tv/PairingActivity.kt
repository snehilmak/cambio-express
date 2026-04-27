package com.dinerobook.tv

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.dinerobook.tv.databinding.ActivityPairingBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Pair-code entry screen.
 *
 * UX:
 *   - Big monospace 6-character input. The Fire TV remote pops up
 *     the system IME on focus; we set inputType=textCapCharacters
 *     so the keyboard auto-uppercases.
 *   - "Pair" button auto-enables when 6 valid chars are entered.
 *   - On success: stash the display_url in Prefs and hand off to
 *     DisplayActivity. The first WebView load is the operator's
 *     "yes, this is the right shop" feedback.
 *   - On failure: show a friendly error, keep the field populated
 *     so the operator can correct a typo without re-typing.
 *
 * Fire TV input notes:
 *   - Default Fire TV IME is the on-screen keyboard. Typing 6 chars
 *     takes ~10s with a remote — acceptable for a one-time setup
 *     flow that runs every several years per shop.
 *   - We do NOT add a custom on-screen keyboard. Platform IME
 *     handles uppercase / autocomplete-off via inputType flags.
 */
class PairingActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPairingBinding
    private lateinit var prefs: Prefs
    private lateinit var api: PairApi

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPairingBinding.inflate(layoutInflater)
        setContentView(binding.root)

        prefs = Prefs(this)
        api   = PairApi(BuildConfig.BASE_URL)

        binding.tvBaseUrl.text = getString(
            R.string.pair_base_url_hint, BuildConfig.BASE_URL,
        )

        binding.btnPair.isEnabled = false
        binding.btnPair.setOnClickListener { submit() }

        binding.codeInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                // Strip non-alphanumerics — operators may paste
                // "ABC-234" or "abc 234" and we want it to just work.
                val raw = s?.toString().orEmpty()
                val cleaned = raw.uppercase().filter { it.isLetterOrDigit() }
                if (cleaned != raw) {
                    binding.codeInput.removeTextChangedListener(this)
                    binding.codeInput.setText(cleaned)
                    binding.codeInput.setSelection(cleaned.length)
                    binding.codeInput.addTextChangedListener(this)
                }
                binding.btnPair.isEnabled = cleaned.length == 6
                binding.tvError.visibility = View.GONE
            }
        })
    }

    private fun submit() {
        val code = binding.codeInput.text?.toString().orEmpty()
        binding.btnPair.isEnabled = false
        binding.btnPair.setText(R.string.pair_button_loading)
        binding.tvError.visibility = View.GONE

        // Friendly device label — surfaces on the admin's "Currently
        // paired" pill so they see "Fire TV — Stick 4K Max" instead
        // of an opaque token.
        val label = "Fire TV — ${Build.MODEL}".take(80)

        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) { api.redeem(code, label) }
            when (result) {
                is PairApi.Result.Success -> {
                    prefs.displayUrl = result.displayUrl
                    startActivity(Intent(this@PairingActivity, DisplayActivity::class.java))
                    finish()
                }
                is PairApi.Result.NotFound -> showError(
                    getString(R.string.pair_error_not_found))
                is PairApi.Result.NetworkError -> showError(
                    getString(R.string.pair_error_network, result.message))
            }
        }
    }

    private fun showError(msg: String) {
        binding.tvError.text = msg
        binding.tvError.visibility = View.VISIBLE
        binding.btnPair.isEnabled = (binding.codeInput.text?.length == 6)
        binding.btnPair.setText(R.string.pair_button)
    }
}
