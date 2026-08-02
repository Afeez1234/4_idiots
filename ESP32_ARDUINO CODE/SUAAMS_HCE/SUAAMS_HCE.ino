/*
  SUAAMS HCE Check-In Terminal
  ESP32 + PN532: reads the short-lived beacon token an Android phone
  broadcasts over NFC HCE (see mint_checkin_beacon in api/student.py and
  SuaamsHceService.kt on the app side) and submits it to Flask.

  This is a SEPARATE sketch from SUAAMS_ESP.ino/SUAAMS_.ino (MFRC522,
  physical card UID flow) -- that flow is untouched and remains a valid
  fallback; this is the new phone-tap path, not a replacement.

  ***BEFORE COMPILING***
  Adafruit_PN532's packet buffer defaults to 64 bytes, which is too small
  for a ~300-byte chunked JWT exchange. This does NOT work as a sketch-level
  #define before #include -- confirmed by reading the library source
  directly: PN532_PACKBUFFSIZ is a plain #define with no #ifndef guard in
  Adafruit_PN532.cpp. You must edit the installed library itself:
    1. Find Adafruit_PN532.cpp in your Arduino libraries folder
       (typically Documents/Arduino/libraries/Adafruit_PN532/).
    2. Change: #define PN532_PACKBUFFSIZ 64
       to:     #define PN532_PACKBUFFSIZ 255
    3. Re-save and re-verify/upload this sketch.
  Without this, inDataExchange() will refuse any exchange longer than ~62
  bytes and every chunked read will fail.

  WIRING ASSUMPTION: I2C (SDA/SCL), matching Adafruit's own most common
  example setup. The existing MFRC522 sketches used SPI -- confirm actual
  wiring once hardware is on the bench. If wired via SPI instead, swap the
  Adafruit_PN532 constructor below for the SPI variant; everything else in
  this file (the protocol logic) is unaffected by that choice.

  KNOWN UNCERTAINTY: inListPassiveTarget()'s ability to fully activate an
  ISO14443-4 (Type 4 / ISO-DEP) target -- what Android HCE emulates -- has
  only been directly confirmed here against elechouse's PN532_HSU fork's
  android_hce.ino example, not Adafruit's unmodified library specifically.
  The API surface is identical, but if inListPassiveTarget() fails
  specifically against the phone while succeeding against a MIFARE card,
  that fork is the concrete fallback, not a library to debug blind.
*/

#include <Wire.h>
#include <Adafruit_PN532.h>
#include <WiFi.h>
#include <HTTPClient.h>

// ---------------- WiFi / Backend ----------------

const char* ssid = "Redmi 13C";
const char* password = "alesh1234";
const char* checkinUrl = "https://suaams.onrender.com/api/v1/student/checkin";


#define SDA_PIN 21
#define SCL_PIN 22
// ---------------- PN532 ----------------
#define PN532_IRQ   (2)
#define PN532_RESET (3)
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

// Must match SuaamsHceService.kt's CHUNK_SIZE. +2 for the trailing
// SW1 SW2 the phone always appends; stays well under the uint8_t 255-byte
// ceiling inDataExchange()'s own signature imposes on a single exchange.
const uint8_t CHUNK_SIZE = 200;
const uint8_t RESPONSE_BUF_SIZE = CHUNK_SIZE + 2;

// Safety cap on GET RESPONSE round-trips -- at 200-byte chunks a ~300-byte
// JWT only ever needs 2 exchanges total. This guards against looping
// forever if a malformed/malicious response keeps claiming "more data".
const uint8_t MAX_EXCHANGES = 10;

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

// Explicit forward declarations -- Arduino normally auto-generates these
// by scanning the sketch with ctags, but ctags misreads apostrophes in the
// header comment above (e.g. the possessive on "Adafruit_PN532") as
// unterminated character literals, which desyncs its parser for the rest
// of the file and makes it silently skip both functions below. Declaring
// them here directly sidesteps that -- and stays correct even if the
// comment text changes again later, rather than depending on nobody ever
// typing an apostrophe above this line.
bool performCheckInExchange(String &outToken);
void submitBeaconToken(const String &token);

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
      // remain" -- not reachable at today's ~300-byte token with 200-byte
      // chunks (max remainder ~100), and Le=0x00 in a GET RESPONSE
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

  HTTPClient http;
  http.begin(checkinUrl);
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
