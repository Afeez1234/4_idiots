package com.suaams.mobile

import android.nfc.cardemulation.HostApduService
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log

/**
 * Broadcasts the short-lived check-in beacon over NFC HCE to the
 * ESP32/PN532 terminal.
 *
 * The token is 32 ASCII characters (see beacon.py on the Flask side: a
 * 12-byte payload + 12-byte truncated HMAC, base64url encoded), so it fits
 * in a SINGLE APDU exchange -- 32 bytes plus a 2-byte status word, 34
 * bytes total.
 *
 * This service used to be a chunked multi-exchange protocol: it served the
 * token 64 bytes at a time using ISO 7816-4 `61 xx` status words and GET
 * RESPONSE chaining, because the token was previously a ~360-byte JWT. That
 * cost six round-trips and ~650ms of continuous RF coupling, which is what
 * made taps unreliable -- the phone has to stay well-coupled for two-thirds
 * of a second, and on this hardware the link was measured degrading after
 * ~119 bytes of transfer. With a 34-byte response the whole exchange is a
 * single frame, so the chunking machinery is gone: no `offset`, no
 * `CHUNK_SIZE`, no GET RESPONSE. There is nothing left to get out of sync.
 *
 * The token lives in the companion object rather than an instance field
 * because it's written from a completely different component --
 * MainActivity's MethodChannel handler -- which has no reference to whatever
 * live SuaamsHceService instance the NFC stack is currently holding.
 */
class SuaamsHceService : HostApduService() {

    companion object {
        private const val TAG = "SuaamsHceService"

        // SELECT AID header (00 A4 04 00). Android's own AID routing in
        // apduservice.xml has already matched the AID before delivering
        // anything here, so we don't re-validate the AID bytes.
        private val SELECT_HEADER = byteArrayOf(0x00, 0xA4.toByte(), 0x04, 0x00)

        private val SW_SUCCESS = byteArrayOf(0x90.toByte(), 0x00)
        // 6A 88 "Referenced data not found" -- returned when a reader taps
        // while no live beacon exists: fresh install, after the window
        // closed, or a stale tap arriving late. The terminal reads this as
        // "nothing to record" rather than as a fault.
        private val SW_NO_TOKEN = byteArrayOf(0x6A, 0x88.toByte())
        // 6D 00 "Instruction not supported" -- anything that isn't SELECT,
        // and the fallback for a malformed/too-short command rather than
        // risking an ArrayIndexOutOfBounds.
        private val SW_INS_NOT_SUPPORTED = byteArrayOf(0x6D, 0x00)

        // Fallback window if Dart doesn't supply a TTL. Matches
        // BEACON_TOKEN_TTL_SECONDS on the Flask side. Dart normally passes
        // the server's own expires_in, so this is only a safety net.
        const val DEFAULT_TTL_MILLIS = 3_000L

        private val handler = Handler(Looper.getMainLooper())

        @Volatile
        private var beaconToken: ByteArray? = null

        // Monotonic deadline (SystemClock.elapsedRealtime, not
        // currentTimeMillis) at which the token above stops being valid.
        //
        // The expiry is enforced HERE, in the process that actually holds
        // the token, rather than by a Dart Timer. That matters because the
        // previous design relied on a Timer in nfc_provider.dart to call
        // clearBeaconToken(), and there were several ways that never ran:
        // the sheet could be dismissed while the biometric prompt was up
        // (the provider disposes, so the timer's ref is dead and both the
        // state write and the cleanup throw on an unmounted ref), or the
        // isolate could be suspended when the app is backgrounded, or the
        // OS could simply throttle the timer. In every one of those cases
        // the token stayed readable in this process.
        //
        // SystemClock.elapsedRealtime() is immune to wall-clock changes and
        // keeps counting while the device sleeps, so the window closes on
        // time no matter what Dart is doing.
        @Volatile
        private var deadlineElapsedMs = 0L

        // HCE is purely passive/reactive -- the phone has no way to know
        // whether a reader is even nearby except by noticing it got asked
        // something. Without this flag, "nothing nearby ever read this" and
        // "something read it but the backend never confirmed" are
        // indistinguishable from Dart, which would otherwise have to wait
        // out the full confirmation-poll window either way.
        @Volatile
        private var tapDetected: Boolean = false

        private val expiryRunnable = Runnable { clearBeaconToken("deadline") }

        /**
         * Arm a beacon for [ttlMillis]. Called from MainActivity's
         * MethodChannel handler right after the server mints one.
         *
         * JWTs are base64url + '.' separators, so plain ASCII encoding is
         * exact -- no multi-byte concerns.
         */
        fun setBeaconToken(token: String, ttlMillis: Long = DEFAULT_TTL_MILLIS) {
            // Cancel any pending self-clear from a previous attempt BEFORE
            // installing the new token. Without this, a token minted a
            // moment after the last one was cleared could be wiped by the
            // previous window's still-queued runnable.
            handler.removeCallbacks(expiryRunnable)

            beaconToken = token.toByteArray(Charsets.US_ASCII)
            deadlineElapsedMs = SystemClock.elapsedRealtime() + ttlMillis
            tapDetected = false
            handler.postDelayed(expiryRunnable, ttlMillis)

            Log.d(
                TAG,
                "Beacon armed: ${token.length} chars, ttl=${ttlMillis}ms " +
                    "(t=${System.currentTimeMillis()})"
            )
        }

        /**
         * Drop the token. Called when the broadcast window closes, on any
         * error before it opened, and -- critically -- by [expiryRunnable]
         * when the deadline passes with no help from Dart at all.
         */
        fun clearBeaconToken(reason: String = "explicit") {
            handler.removeCallbacks(expiryRunnable)

            // Zero the bytes before dropping the reference. The array lives
            // in a process-lifetime companion object, so nulling alone
            // leaves the credential recoverable in the heap until GC runs.
            val token = beaconToken
            if (token != null) {
                token.fill(0)
            }

            beaconToken = null
            deadlineElapsedMs = 0L
            // Reset here too, not just in setBeaconToken. wasTapDetected()
            // is read after the window closes, and the invariant "a fresh
            // attempt starts with tapDetected == false" has to hold in one
            // place or it silently breaks when a new field is added.
            tapDetected = false

            Log.d(TAG, "Beacon cleared (reason=$reason, t=${System.currentTimeMillis()})")
        }

        /** Did any reader engage our AID since the last setBeaconToken()? */
        fun wasTapDetected(): Boolean = tapDetected

        /** Is a token live right now? Used by processCommandApdu. */
        private fun liveToken(): ByteArray? {
            val token = beaconToken ?: return null
            if (SystemClock.elapsedRealtime() >= deadlineElapsedMs) {
                // The Handler self-clear is the primary mechanism; this is
                // the backstop for the case where it was delayed (main
                // thread busy, process frozen). A reader must never be
                // handed a credential past its window.
                Log.w(TAG, "Deadline passed but token not yet cleared; refusing to serve it")
                clearBeaconToken("deadline-backstop")
                return null
            }
            return token
        }
    }

    override fun processCommandApdu(commandApdu: ByteArray?, extras: Bundle?): ByteArray {
        val now = System.currentTimeMillis()

        // Android only calls this once our AID has already been matched via
        // apduservice.xml routing -- reaching this line at all, for ANY
        // command, already proves a reader engaged specifically with us.
        // Set before the malformed-command check so a garbled first command
        // still counts as "something was there".
        tapDetected = true

        val commandStr = commandApdu?.joinToString("") { "%02X".format(it) } ?: "NULL"
        Log.d(TAG, "Received APDU: $commandStr (t=$now)")

        if (commandApdu == null || commandApdu.size < 4) {
            Log.w(TAG, "Malformed/too-short APDU (t=$now)")
            return SW_INS_NOT_SUPPORTED
        }

        val header = commandApdu.copyOfRange(0, 4)
        if (!header.contentEquals(SELECT_HEADER)) {
            Log.w(TAG, "Unrecognized APDU header (t=$now)")
            return SW_INS_NOT_SUPPORTED
        }

        val token = liveToken()
        if (token == null) {
            Log.w(TAG, "SELECT with no live beacon -> SW_NO_TOKEN (t=$now)")
            return SW_NO_TOKEN
        }

        // Single-shot: the whole token, plus 90 00. No 61xx, no GET
        // RESPONSE, no offset to track.
        Log.d(TAG, "SELECT -> serving ${token.size} bytes in one response (t=$now)")
        return token + SW_SUCCESS
    }

    override fun onDeactivated(reason: Int) {
        // The tap ended (field lost) or the card was deselected. The token
        // is NOT cleared here: its lifetime is tied to the broadcast
        // window, not to individual field-loss events -- RF can drop and
        // re-couple mid-tap without the logical session ending, and
        // wiping on every deactivation would strand a student mid-transfer.
        // The native deadline is what actually bounds the window.
        val reasonName = if (reason == DEACTIVATION_LINK_LOSS) "LINK_LOSS" else "DESELECTED"
        Log.d(TAG, "Deactivated: $reasonName (t=${System.currentTimeMillis()})")
    }
}
