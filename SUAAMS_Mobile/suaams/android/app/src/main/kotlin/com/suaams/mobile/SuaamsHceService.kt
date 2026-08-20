package com.suaams.mobile

import android.nfc.cardemulation.HostApduService
import android.os.Bundle
import android.util.Log

/**
 * Broadcasts the short-lived beacon token (minted by
 * api/student.py's mint_checkin_beacon, ~300 bytes as a JWT) over NFC HCE
 * to the ESP32/PN532 terminal.
 *
 * The token doesn't fit in a single APDU exchange -- the PN532 side (via
 * the Adafruit_PN532 Arduino library, patched PN532_PACKBUFFSIZ=255) caps
 * out around ~250 usable bytes per InDataExchange call. So this implements
 * the standard ISO 7816-4 idiom for "response bigger than one frame":
 * return as much as fits plus status word 61 xx (xx = bytes still
 * available), and answer a follow-up GET RESPONSE (00 C0 00 00 ...) with
 * the next slice, repeating until 90 00.
 *
 * beaconToken lives in the companion object (not as an instance field)
 * because it's written from a completely different component --
 * MainActivity's MethodChannel handler, which has no reference to whatever
 * live SuaamsHceService instance the NFC stack is currently holding. The
 * chunk offset stays a plain instance var: unlike the token itself, it's
 * only ever read/written from processCommandApdu/onDeactivated, both
 * always invoked on the one instance the system is currently driving.
 */
class SuaamsHceService : HostApduService() {

    companion object {
        // Logging is here specifically because we're skipping the
        // isolated (second-phone) pre-test and going straight to real
        // PN532 hardware -- if a tap fails end-to-end, this is the only
        // visibility into what happened on the Android side specifically,
        // as opposed to the ESP32/PN532 side or the Flask side. Every line
        // carries both an epoch-ms timestamp (to line up against the
        // ESP32's own serial log and the Flask server log, which use wall
        // clock too) and an elapsed-since-SELECT figure (to see how long
        // the exchange itself is taking, independent of clock sync issues
        // between devices).
        private const val TAG = "SuaamsHceService"

        // Originally 200 (margin below the ~250-byte PN532/Adafruit_PN532
        // buffer ceiling). Dropped to 64 after real hardware testing showed
        // 200-byte exchanges corrupting mid-transfer -- a hex dump of a
        // failed read showed genuine JWT bytes for the first ~119 bytes,
        // then the RF coupling apparently dropped, with the rest of the
        // buffer coming back as padding (0x80 repeated) instead of real
        // data or a real status word.
        //
        // 64 then proved fully reliable end-to-end (6/6 clean chunks, zero
        // corruption on a real tap), but paid for that with round-trip
        // count: ~6 exchanges for a ~360-byte token, and each APDU
        // round-trip has fixed overhead on top of the RF transfer itself --
        // that pushed total exchange time past 650ms, eating deep into
        // BEACON_TOKEN_TTL_SECONDS's 3-second budget once the Flask POST
        // (which can itself run 1-2s on a cold Render dyno, see /healthz in
        // app.py) is added on top. Raised to 96 as a middle ground: still
        // comfortably under the ~119-byte point where the 200-byte exchange
        // is known to have destabilized, but cuts the same token down to
        // ~4 round-trips instead of 6. Single named constant, same pattern
        // as BEACON_TOKEN_TTL_SECONDS on the Flask side, so it's a one-line
        // change if real-world testing says it needs to move again.
        private const val CHUNK_SIZE = 64

        private val SELECT_HEADER = byteArrayOf(0x00, 0xA4.toByte(), 0x04, 0x00)
        private val GET_RESPONSE_HEADER = byteArrayOf(0x00, 0xC0.toByte(), 0x00, 0x00)

        private val SW_SUCCESS = byteArrayOf(0x90.toByte(), 0x00)
        // 6A 88 "Referenced data not found" -- returned when a reader taps
        // while no beacon token has been set yet (fresh install) or after
        // clearBeaconToken() ran, rather than crashing or returning
        // garbage. The ESP32 gets an unambiguous "nothing to read" signal.
        private val SW_NO_TOKEN = byteArrayOf(0x6A, 0x88.toByte())
        // 6D 00 "Instruction not supported" -- anything that isn't SELECT
        // or GET RESPONSE. Also the fallback for a malformed/too-short
        // command rather than risking an ArrayIndexOutOfBounds.
        private val SW_INS_NOT_SUPPORTED = byteArrayOf(0x6D, 0x00)

        @Volatile
        private var beaconToken: ByteArray? = null

        // HCE is purely passive/reactive -- the phone has no way to know
        // whether a reader is even nearby except by noticing it got asked
        // something. Without this flag, "nothing nearby ever read this"
        // and "something read it but the backend never confirmed" are
        // indistinguishable from the Dart side, which otherwise has to
        // wait out the full confirmation-poll window either way.
        @Volatile
        private var tapDetected: Boolean = false

        /** Called from MainActivity's MethodChannel handler right before
         * each broadcast attempt (mirrors mint_checkin_beacon being called
         * fresh per tap, not reused). JWTs are base64url + '.' separators,
         * so plain ASCII encoding is exact -- no multi-byte concerns. */
        fun setBeaconToken(token: String) {
            beaconToken = token.toByteArray(Charsets.US_ASCII)
            tapDetected = false
            Log.d(TAG, "Beacon token set: ${token.length} chars (t=${System.currentTimeMillis()})")
        }

        /** Called from the same handler when the 3-second broadcast window
         * closes, or on any error before that window starts. Defense in
         * depth on top of the token's own short expiry -- a tap arriving
         * after this point gets SW_NO_TOKEN instead of a stale token. */
        fun clearBeaconToken() {
            beaconToken = null
            Log.d(TAG, "Beacon token cleared (t=${System.currentTimeMillis()})")
        }

        /** True if any reader engaged our AID (i.e. processCommandApdu ran
         * at all, for any command) since the last setBeaconToken() call.
         * Checked once the 3-second broadcast window closes -- if false,
         * there's nothing for confirmation polling to ever find, so the
         * Dart side can skip straight to "no terminal detected" instead of
         * waiting out its full poll window for something that could never
         * have succeeded. */
        fun wasTapDetected(): Boolean = tapDetected
    }

    private var offset = 0
    // Wall-clock time of the current session's SELECT AID, used only to
    // compute "elapsed" in the per-chunk log lines below -- reset each time
    // a new SELECT starts a session, same as offset.
    private var sessionStartTime = 0L

    override fun processCommandApdu(commandApdu: ByteArray?, extras: Bundle?): ByteArray {
        val now = System.currentTimeMillis()

        // Android only calls this once our AID has already been matched
        // via apduservice.xml's routing -- reaching this line at all, for
        // ANY command (even a malformed one), already proves a reader
        // engaged specifically with us. Set unconditionally, before the
        // malformed-command check below, so a garbled first command still
        // counts as "something was there".
        tapDetected = true

        val commandStr = commandApdu?.joinToString("") { "%02X".format(it) } ?: "NULL"
        Log.d(TAG, "Received APDU: $commandStr (t=$now)")

        if (commandApdu == null || commandApdu.size < 4) {
            Log.w(TAG, "Malformed/too-short APDU (t=$now)")
            return SW_INS_NOT_SUPPORTED
        }

        val header = commandApdu.copyOfRange(0, 4)

        return when {
            header.contentEquals(SELECT_HEADER) -> {
                // Android's own AID routing (apduservice.xml) already
                // confirmed this SELECT matched our AID before delivering
                // it here -- no need to re-validate the AID bytes.
                offset = 0
                sessionStartTime = now
                val tokenLen = beaconToken?.size ?: -1
                Log.d(TAG, "SELECT AID matched, token=$tokenLen bytes (t=$now, elapsed=0ms)")
                nextChunk(now)
            }
            header.contentEquals(GET_RESPONSE_HEADER) -> nextChunk(now)
            else -> {
                Log.w(TAG, "Unrecognized APDU header ${header.joinToString("") { "%02X".format(it) }} (t=$now)")
                SW_INS_NOT_SUPPORTED
            }
        }
    }

    private fun nextChunk(now: Long): ByteArray {
        val elapsed = now - sessionStartTime
        val token = beaconToken
        if (token == null) {
            Log.w(TAG, "No beacon token set, returning SW_NO_TOKEN (t=$now, elapsed=${elapsed}ms)")
            return SW_NO_TOKEN
        }

        val remaining = token.size - offset
        if (remaining <= 0) {
            // GET RESPONSE called again after the final chunk already went
            // out -- shouldn't happen in a well-behaved exchange, but
            // logged rather than silently returning success, since it
            // would otherwise look identical to a normal final ACK.
            Log.w(TAG, "GET RESPONSE with nothing left to send (t=$now, elapsed=${elapsed}ms)")
            return SW_SUCCESS
        }

        val chunkLen = minOf(CHUNK_SIZE, remaining)
        val chunkIndex = offset / CHUNK_SIZE
        val chunk = token.copyOfRange(offset, offset + chunkLen)
        offset += chunkLen

        val stillRemaining = token.size - offset
        return if (stillRemaining > 0) {
            // SW2 can only represent up to 255 in one byte; 0x00 is the
            // ISO 7816-4 sentinel for "256 or more bytes still available".
            // Not reachable at today's ~300-byte token size with 64-byte
            // chunks (max remainder is ~63), but correct if the token
            // shape ever grows.
            val sw2 = if (stillRemaining > 255) 0 else stillRemaining
            Log.d(TAG, "Sent chunk #$chunkIndex: $chunkLen bytes, $stillRemaining remaining, more data follows (t=$now, elapsed=${elapsed}ms)")
            chunk + byteArrayOf(0x61, sw2.toByte())
        } else {
            Log.d(TAG, "Sent chunk #$chunkIndex: $chunkLen bytes, final chunk (t=$now, elapsed=${elapsed}ms)")
            chunk + SW_SUCCESS
        }
    }

    override fun onDeactivated(reason: Int) {
        // Field lost (tap ended) or a new SELECT is about to start a fresh
        // session -- either way, don't let a stale offset leak into the
        // next exchange. The token itself isn't cleared here: that's
        // clearBeaconToken()'s job, tied to the 3-second window closing,
        // not to individual field-loss events (RF can drop and re-couple
        // mid-tap on some hardware without the logical session ending).
        val now = System.currentTimeMillis()
        val elapsed = if (sessionStartTime > 0) now - sessionStartTime else -1
        val reasonName = if (reason == DEACTIVATION_LINK_LOSS) "LINK_LOSS" else "DESELECTED"
        Log.d(TAG, "Deactivated: $reasonName, session lasted ${elapsed}ms (t=$now)")
        offset = 0
    }
}
