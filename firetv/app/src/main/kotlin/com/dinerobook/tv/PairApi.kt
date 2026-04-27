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
 * HTTP wrapper around POST /api/tv-pair/redeem.
 *
 * The backend returns:
 *   200 {"device_token": "...", "display_url": "...", "store_name": "...", "title": "..."}
 *   404 {"error": "not_found"}        — every failure mode is 404 by
 *                                        design (no oracle for brute force).
 *
 * The app cares about [Result.Success.displayUrl] above all — that's
 * what we hand to the WebView. store_name + title are surfaced
 * briefly on the success screen for a moment of "yes, you paired
 * the right shop" feedback.
 */
class PairApi(baseUrl: String) {

    private val endpoint = baseUrl.trimEnd('/') + "/api/tv-pair/redeem"
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    sealed class Result {
        data class Success(
            val deviceToken: String,
            val displayUrl: String,
            val storeName: String,
            val title: String,
        ) : Result()
        data class NotFound(val httpStatus: Int) : Result()  // 404 from the server
        data class NetworkError(val message: String) : Result()
    }

    /**
     * Blocking — the caller is responsible for running this on
     * Dispatchers.IO (PairingActivity does so via a coroutine).
     */
    fun redeem(rawCode: String, deviceLabel: String? = null): Result {
        val cleaned = rawCode.uppercase().filter { it.isLetterOrDigit() }
        if (cleaned.length != 6) return Result.NotFound(0)

        val body = JSONObject().apply {
            put("code", cleaned)
            if (!deviceLabel.isNullOrBlank()) put("device_label", deviceLabel)
        }.toString().toRequestBody(JSON)

        val req = Request.Builder()
            .url(endpoint)
            .header("Accept", "application/json")
            .header("User-Agent", USER_AGENT)
            .post(body)
            .build()

        return try {
            client.newCall(req).execute().use { resp ->
                val raw = resp.body?.string().orEmpty()
                if (!resp.isSuccessful) return Result.NotFound(resp.code)
                val json = JSONObject(raw)
                Result.Success(
                    deviceToken = json.optString("device_token"),
                    displayUrl  = json.optString("display_url"),
                    storeName   = json.optString("store_name"),
                    title       = json.optString("title"),
                )
            }
        } catch (e: IOException) {
            Result.NetworkError(e.message ?: "Network error")
        } catch (e: Exception) {
            // Malformed JSON, etc. — treat as "not paired" rather than
            // crashing.
            Result.NetworkError(e.message ?: "Unexpected error")
        }
    }

    companion object {
        private val JSON = "application/json; charset=utf-8".toMediaType()

        // Conservative UA so logs show what's calling the redeem
        // endpoint (helpful when triaging billing-vs-pairing issues).
        private val USER_AGENT = "DineroBookTV/1.0 (Android ${Build.VERSION.RELEASE}; ${Build.MODEL})"
    }
}
