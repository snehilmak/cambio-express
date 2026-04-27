package com.dinerobook.tv

import android.os.Build
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * HTTP wrapper around the inverted pair-code flow.
 *
 *   1. [init] — POST /api/tv-pair/init. Server creates a
 *      TVPendingPair row and returns a 6-char code + a stable
 *      device_token. The TV displays the code; the operator types
 *      it into /tv-display in their admin browser.
 *
 *   2. [pollStatus] — GET /api/tv-pair/status?token=<device_token>.
 *      The TV polls every ~2 seconds. Status is "pending" until
 *      the operator claims, "claimed" once they do (carries the
 *      per-device URL the WebView should load), or "expired" if
 *      the code aged out (TV should re-init).
 *
 * The device_token is stable across the pending → paired
 * transition — we never have to rotate it on the client.
 */
class PairApi(baseUrl: String) {

    private val initUrl   = baseUrl.trimEnd('/') + "/api/tv-pair/init"
    private val statusUrl = baseUrl.trimEnd('/') + "/api/tv-pair/status"

    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    sealed class InitResult {
        data class Success(
            val code: String,
            val deviceToken: String,
            val ttlSeconds: Int,
        ) : InitResult()
        data class Error(val message: String) : InitResult()
    }

    sealed class StatusResult {
        data class Pending(val code: String, val ttlSeconds: Int) : StatusResult()
        data class Claimed(
            val displayUrl: String,
            val storeName: String,
            val title: String,
        ) : StatusResult()
        object Expired : StatusResult()
        data class Error(val message: String) : StatusResult()
    }

    /**
     * Blocking — caller is responsible for off-main-thread.
     * Body carries an optional device_label (e.g. "Fire TV — Stick
     * 4K Max") that surfaces on the admin's "Currently paired" pill.
     */
    fun init(deviceLabel: String? = null): InitResult {
        val body = JSONObject().apply {
            if (!deviceLabel.isNullOrBlank()) put("device_label", deviceLabel)
        }.toString().toRequestBody(JSON)

        val req = Request.Builder()
            .url(initUrl)
            .header("Accept", "application/json")
            .header("User-Agent", USER_AGENT)
            .post(body)
            .build()

        return try {
            client.newCall(req).execute().use { resp ->
                val raw = resp.body?.string().orEmpty()
                if (!resp.isSuccessful) {
                    return InitResult.Error("HTTP ${resp.code}")
                }
                val json = JSONObject(raw)
                InitResult.Success(
                    code        = json.optString("code"),
                    deviceToken = json.optString("device_token"),
                    ttlSeconds  = json.optInt("ttl_seconds", 600),
                )
            }
        } catch (e: IOException) {
            InitResult.Error(e.message ?: "Network error")
        } catch (e: Exception) {
            InitResult.Error(e.message ?: "Unexpected error")
        }
    }

    /**
     * Blocking — call from a coroutine on Dispatchers.IO.
     */
    fun pollStatus(deviceToken: String): StatusResult {
        val url = "$statusUrl?token=${java.net.URLEncoder.encode(deviceToken, "UTF-8")}"
        val req = Request.Builder()
            .url(url)
            .header("Accept", "application/json")
            .header("User-Agent", USER_AGENT)
            .get()
            .build()

        return try {
            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) {
                    return StatusResult.Error("HTTP ${resp.code}")
                }
                val json = JSONObject(resp.body?.string().orEmpty())
                when (json.optString("status")) {
                    "pending" -> StatusResult.Pending(
                        code = json.optString("code"),
                        ttlSeconds = json.optInt("ttl_seconds", 0),
                    )
                    "claimed" -> StatusResult.Claimed(
                        displayUrl = json.optString("display_url"),
                        storeName  = json.optString("store_name"),
                        title      = json.optString("title"),
                    )
                    else -> StatusResult.Expired
                }
            }
        } catch (e: IOException) {
            StatusResult.Error(e.message ?: "Network error")
        } catch (e: Exception) {
            StatusResult.Error(e.message ?: "Unexpected error")
        }
    }

    companion object {
        private val JSON = "application/json; charset=utf-8".toMediaType()
        private val USER_AGENT =
            "DineroBookTV/1.0 (Android ${Build.VERSION.RELEASE}; ${Build.MODEL})"
    }
}
