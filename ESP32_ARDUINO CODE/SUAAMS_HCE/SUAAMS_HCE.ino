/*
  SUAAMS HCE Check-In Terminal
  ESP32 + PN532: reads the short-lived beacon token an Android phone
  broadcasts over NFC HCE (see mint_checkin_beacon in api/student.py and
  SuaamsHceService.kt on the app side) and submits it to Flask.
*/

#include <Wire.h>
#include <Adafruit_PN532.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
// ---------------- WiFi / Backend ----------------

const char* ssid = "Abdul-Afeez's S24";
const char* password = "vnix7920";
const char* checkinUrl = "https://suaams.onrender.com/api/v1/student/checkin";


#define SDA_PIN 21
#define SCL_PIN 22
// ---------------- PN532 ----------------
#define PN532_IRQ   -1
#define PN532_RESET -1
Adafruit_PN532 nfc(PN532_IRQ, PN532_RESET);

// ---------------- Protocol constants ----------------
// AID F0394148148100 -- must match apduservice.xml / SuaamsHceService.kt
// exactly, or Android's own AID routing never delivers SELECT to our
// service in the first place.
const uint8_t SELECT_APDU[] = {
  0x00, 0xA4, 0x04, 0x00, 0x07,
  0xF0, 0x39, 0x41, 0x48, 0x14, 0x81, 0x00,
  0x00
};

// Must match SuaamsHceService.kt's CHUNK_SIZE exactly. Originally 200
// (margin below the uint8_t 255-byte ceiling inDataExchange() imposes),
// dropped to 64 after real hardware testing showed 200-byte exchanges
// corrupting mid-transfer -- a raw hex dump of a failed read showed real
// JWT bytes for ~119 bytes, then the RF coupling apparently dropped, with
// the rest of the buffer coming back as padding instead of real data or a
// real status word.
//
// 64 then proved fully reliable on a real tap (6/6 clean chunks, 361 bytes
// reassembled with zero corruption), but the resulting ~650ms exchange time
// (6 round-trips, each with fixed APDU overhead on top of the RF transfer)
// eats deep into BEACON_TOKEN_TTL_SECONDS's 3-second budget once the Flask
// POST is added on top -- POST alone measured ~1.8s against a cold Render
// dyno, enough on its own to expire the token before it's even validated
// (see /healthz in app.py, added to keep that dyno warm). Raised to 96 as a
// middle ground: still comfortably under the ~119-byte point where the
// 200-byte exchange is known to have destabilized, but cuts the same token
// down to ~4 round-trips instead of 6.
const uint8_t CHUNK_SIZE = 64;
const uint8_t RESPONSE_BUF_SIZE = CHUNK_SIZE + 2;

// Safety cap on GET RESPONSE round-trips. At 96-byte chunks a ~360-byte
// JWT needs ~4 exchanges (SELECT + ~3 GET RESPONSEs); capped well above
// that for headroom rather than tuned tight to today's token size. This
// guards against looping forever if a malformed/malicious response keeps
// claiming "more data".
const uint8_t MAX_EXCHANGES = 15;

// No stable per-tap identity to debounce by (a fresh token exists every
// tap, unlike the MFRC522 flow's static card UID) -- throttle by attempt
// cadence instead: don't start a new read cycle until this cooldown has
// elapsed since the last one FINISHED (success, failure, or no-token).
// Actual duplicate-attendance prevention is the backend's
// already_recorded check, not this.
const uint16_t READ_COOLDOWN_MS = 2000;
unsigned long lastAttemptEnd = 0;

// Status words
const uint8_t SW_MORE_DATA  = 0x61;
const uint8_t SW1_SUCCESS   = 0x90;
const uint8_t SW2_SUCCESS   = 0x00;
const uint8_t SW1_NO_TOKEN  = 0x6A;
const uint8_t SW2_NO_TOKEN  = 0x88;

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("[BOOT] SUAAMS HCE terminal starting...");

  Wire.begin(SDA_PIN,SCL_PIN);
  nfc.begin();

  uint32_t versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.println("[FATAL] PN532 not found -- check wiring/interface selection.");
    while (1) {
      delay(1000);
    }
  }
  Serial.print("[BOOT] Found PN532, firmware v");
  Serial.print((versiondata >> 16) & 0xFF, DEC);
  Serial.print('.');
  Serial.println((versiondata >> 8) & 0xFF, DEC);

  nfc.SAMConfig();

  WiFi.begin(ssid, password);
  Serial.print("[BOOT] Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print('.');
  }
  Serial.println();
  Serial.print("[BOOT] WiFi connected, IP ");
  Serial.println(WiFi.localIP());
  Serial.println("[BOOT] Ready, waiting for taps...");
}

void loop() {
  if (millis() - lastAttemptEnd < READ_COOLDOWN_MS) {
    return;
  }

  bool targetFound = nfc.inListPassiveTarget();
  if (!targetFound) {
    return; // nothing in the field right now
  }

  Serial.println("[TAP] Target detected, starting exchange...");
  unsigned long exchangeStart = millis();

  String token = "";
  bool gotToken = performCheckInExchange(token);

  unsigned long exchangeDuration = millis() - exchangeStart;
  Serial.print("[TAP] Exchange finished in ");
  Serial.print(exchangeDuration);
  Serial.println("ms");

  if (gotToken && token.length() > 0) {
    submitBeaconToken(token);
  }

  lastAttemptEnd = millis();
}

// Diagnostic-only: dumps the raw bytes of a response exactly as received,
// before any interpretation. Added specifically to check whether the
// trailing two bytes we're reading as SW1/SW2 really are what's arriving
// over the air, or whether something upstream (PN532 framing, buffer
// indexing) is shifting/truncating the response -- a computed SW=8080
// doesn't match anything SuaamsHceService.kt can send (61 xx / 90 00 /
// 6A 88), so seeing the raw bytes is the fastest way to tell "wrong bytes
// arrived" apart from "right bytes, misread".
void printHexDump(const char* label, uint8_t* buf, uint8_t len) {
  Serial.print(label);
  Serial.print(" (");
  Serial.print(len);
  Serial.print(" bytes): ");
  for (uint8_t i = 0; i < len; i++) {
    if (buf[i] < 0x10) Serial.print('0');
    Serial.print(buf[i], HEX);
    Serial.print(' ');
  }
  Serial.println();
}

// Runs SELECT AID, then follows the phone's 61xx/90 00 status words with
// GET RESPONSE calls until the token is fully reassembled. Returns false
// (with a logged reason) for a failed exchange OR the legitimate "no
// token set on the phone right now" case -- the caller doesn't need to
// tell those apart beyond "nothing to POST".
bool performCheckInExchange(String &outToken) {
  uint8_t response[RESPONSE_BUF_SIZE];
  uint8_t responseLength = sizeof(response);

  Serial.println("[APDU] -> SELECT AID");
  bool ok = nfc.inDataExchange((uint8_t*)SELECT_APDU, sizeof(SELECT_APDU), response, &responseLength);

  if (!ok || responseLength < 2) {
    Serial.println("[APDU] SELECT failed or returned a malformed response");
    return false;
  }

  outToken = "";
  uint8_t exchangeCount = 0;

  while (true) {
    if (exchangeCount >= MAX_EXCHANGES) {
      Serial.println("[APDU] Exceeded max exchange count, aborting (possible malformed peer)");
      return false;
    }

    if (responseLength < 2) {
      Serial.println("[APDU] Response too short to contain a status word, aborting");
      return false;
    }

    printHexDump("[APDU] raw response", response, responseLength);

    uint8_t sw1 = response[responseLength - 2];
    uint8_t sw2 = response[responseLength - 1];
    uint8_t dataLen = responseLength - 2;

    Serial.print("[APDU] chunk ");
    Serial.print(exchangeCount);
    Serial.print(": ");
    Serial.print(dataLen);
    Serial.print(" bytes, SW=");
    Serial.print(sw1, HEX);
    Serial.println(sw2, HEX);

    if (sw1 == SW1_NO_TOKEN && sw2 == SW2_NO_TOKEN) {
      Serial.println("[APDU] No beacon token set on phone right now (not an error)");
      return false;
    }

    for (uint8_t i = 0; i < dataLen; i++) {
      outToken += (char)response[i];
    }
    exchangeCount++;

    if (sw1 == SW1_SUCCESS && sw2 == SW2_SUCCESS) {
      Serial.print("[APDU] Reassembly complete, ");
      Serial.print(outToken.length());
      Serial.println(" bytes");
      return true;
    }

    if (sw1 == SW_MORE_DATA) {
      // sw2 == 0x00 would be the ISO 7816-4 sentinel for ">=256 bytes
      // remain" -- not reachable at today's ~300-byte token with 64-byte
      // chunks (max remainder ~63), and Le=0x00 in a GET RESPONSE
      // conventionally means "as many bytes as available" anyway, so no
      // special-case handling needed even if it were hit.
      uint8_t remaining = sw2;
      Serial.print("[APDU] -> GET RESPONSE, Le=");
      Serial.println(remaining);

      uint8_t getResponseApdu[] = {0x00, 0xC0, 0x00, 0x00, remaining};
      responseLength = sizeof(response); // reset capacity before reuse
      ok = nfc.inDataExchange(getResponseApdu, sizeof(getResponseApdu), response, &responseLength);

      if (!ok) {
        Serial.println("[APDU] GET RESPONSE failed");
        return false;
      }
      continue;
    }

    Serial.println("[APDU] Unexpected status word, aborting exchange");
    return false;
  }
}

void submitBeaconToken(const String &token) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[POST] WiFi not connected, dropping this attempt");
    return;
  }

  // Create a secure client and tell it to bypass SSL certificate validation
  WiFiClientSecure client;
  client.setInsecure(); 
  
  HTTPClient http;
  http.begin(client,checkinUrl);
  http.addHeader("Content-Type", "application/json");

  String payload = "{\"beacon_token\":\"" + token + "\"}";

  // Timed separately from the APDU exchange above on purpose: a slow
  // Render free-tier cold start (multi-second) shows up here as a large
  // [POST] duration, not folded into [TAP] exchange timing -- if a beacon
  // token expires (3s TTL) and THIS number is the large one, that's a
  // cold-start/network issue, not a chunking bug.
  Serial.println("[POST] Submitting beacon_token to /api/v1/student/checkin");
  unsigned long postStart = millis();
  int httpResponseCode = http.POST(payload);
  unsigned long postDuration = millis() - postStart;

  String responseBody = http.getString();

  Serial.print("[POST] Completed in ");
  Serial.print(postDuration);
  Serial.println("ms");
  Serial.print("[POST] HTTP ");
  Serial.print(httpResponseCode);
  Serial.print(": ");
  Serial.println(responseBody);

  http.end();
}
