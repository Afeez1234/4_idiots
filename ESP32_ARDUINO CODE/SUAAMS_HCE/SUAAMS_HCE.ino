/*
  SUAAMS HCE Check-In Terminal
  ESP32 + PN532: reads the short-lived check-in beacon an Android phone
  broadcasts over NFC HCE and submits it to Flask.

  Single-exchange reader
  ----------------------
  The phone's HCE service (SuaamsHceService.kt) answers a SELECT with the
  whole beacon plus a 90 00 status word -- 34 bytes, one frame. This sketch
  used to be a chunked multi-exchange protocol: SELECT, then GET RESPONSE
  in 64-byte slices following 61xx status words, six round-trips and ~650ms
  of continuous RF coupling. That was needed only because the beacon used
  to be a ~360-byte JWT. The link was measured degrading after ~119 bytes of
  transfer, so a long multi-frame exchange meant the phone had to stay
  well-coupled for two-thirds of a second -- which is why taps were
  unreliable, and why detection looked intermittent.

  With a 34-byte response the whole read is one frame, so all of that is
  gone: no CHUNK_SIZE to tune, no GET RESPONSE loop, no 61xx to parse, no
  offset to track, and roughly 13x more tolerance for the phone drifting
  during the tap.
*/

#include <Wire.h>
#include <Adafruit_PN532.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

#include "secrets.h"  // WiFi + terminal credentials. NOT in git.

#define SDA_PIN 21
#define SCL_PIN 22

// ---------------- PN532 ----------------
#define PN532_IRQ   -1
#define PN532_RESET -1
Adafruit_PN532 nfc(PN532_IRQ, PN532_RESET);

// ---------------- Protocol ----------------
// AID F0394148148100 -- must match apduservice.xml / SuaamsHceService.kt
// exactly, or Android's own AID routing never delivers SELECT to our
// service in the first place.
const uint8_t SELECT_APDU[] = {
  0x00, 0xA4, 0x04, 0x00, 0x07,
  0xF0, 0x39, 0x41, 0x48, 0x14, 0x81, 0x00,
  0x00
};

// One response frame: 32-char beacon + 2-byte status word. Sized with
// headroom rather than exactly, so a slightly longer future token can't
// overflow the buffer.
const uint8_t RESPONSE_BUF_SIZE = 64;

// Status words
const uint8_t SW1_SUCCESS  = 0x90;
const uint8_t SW2_SUCCESS  = 0x00;
const uint8_t SW1_NO_TOKEN = 0x6A;
const uint8_t SW2_NO_TOKEN = 0x88;

// Throttle repeated reads of one held phone. This is only a cadence guard
// -- it is NOT the duplicate-attendance defence, which is the backend's
// already_recorded check.
const uint16_t READ_COOLDOWN_MS = 2000;
unsigned long lastAttemptEnd = 0;

// WiFi must not be able to brick the terminal at boot. The old code
// looped `while (WiFi.status() != WL_CONNECTED)` forever inside setup(),
// so an AP outage at power-on wedged the board until someone physically
// power-cycled it, and it re-wedged on every subsequent outage. Now:
// bounded wait, then carry on in a degraded state, with a non-blocking
// reconnect in loop().
const unsigned long WIFI_CONNECT_TIMEOUT_MS = 20000;
const unsigned long WIFI_RETRY_INTERVAL_MS = 5000;
unsigned long lastWifiAttempt = 0;
bool wifiReady = false;

// ---------------- Helpers ----------------

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

bool connectWifi() {
  Serial.print("[WIFI] Connecting");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_CONNECT_TIMEOUT_MS) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[WIFI] Connected, IP ");
    Serial.println(WiFi.localIP());
    wifiReady = true;
    return true;
  }

  // Not fatal. The terminal still scans for taps; the POST will simply be
  // skipped until WiFi comes back, and the app will report "could not
  // confirm" rather than a false success.
  Serial.println("[WIFI] Connect timed out -- continuing offline, will retry in background");
  wifiReady = false;
  return false;
}

// Keeps WiFi alive without ever blocking the NFC loop. Called on every
// pass through loop(); returns immediately unless a retry is due.
void maintainWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    wifiReady = true;
    return;
  }

  wifiReady = false;
  if (millis() - lastWifiAttempt < WIFI_RETRY_INTERVAL_MS) {
    return;
  }
  lastWifiAttempt = millis();

  Serial.println("[WIFI] Link down, reconnecting...");
  WiFi.reconnect();
}

// Runs SELECT and reads the beacon in a SINGLE exchange. Returns false for
// a failed read or the legitimate "phone has no beacon armed" case --
// the caller doesn't need to tell those apart beyond "nothing to POST".
bool readBeacon(String &outToken) {
  uint8_t response[RESPONSE_BUF_SIZE];
  uint8_t responseLength = sizeof(response);

  Serial.println("[APDU] -> SELECT AID");
  bool ok = nfc.inDataExchange((uint8_t*)SELECT_APDU, sizeof(SELECT_APDU), response, &responseLength);

  if (!ok || responseLength < 2) {
    Serial.print("[APDU] SELECT failed (ok=");
    Serial.print(ok);
    Serial.print(", len=");
    Serial.print(responseLength);
    Serial.println(")");
    return false;
  }

  printHexDump("[APDU] raw response", response, responseLength);

  uint8_t sw1 = response[responseLength - 2];
  uint8_t sw2 = response[responseLength - 1];
  uint8_t dataLen = responseLength - 2;

  if (sw1 == SW1_NO_TOKEN && sw2 == SW2_NO_TOKEN) {
    Serial.println("[APDU] No beacon armed on phone right now (not an error)");
    return false;
  }

  if (sw1 != SW1_SUCCESS || sw2 != SW2_SUCCESS) {
    Serial.print("[APDU] Unexpected status word: ");
    Serial.print(sw1, HEX);
    Serial.print(' ');
    Serial.println(sw2, HEX);
    return false;
  }

  outToken = "";
  for (uint8_t i = 0; i < dataLen; i++) {
    outToken += (char)response[i];
  }

  Serial.print("[APDU] Beacon read in ONE exchange: ");
  Serial.print(outToken.length());
  Serial.println(" bytes");
  return true;
}

void submitBeaconToken(const String &token) {
  if (!wifiReady || WiFi.status() != WL_CONNECTED) {
    // Previously this returned silently, so a tap during a WiFi blip
    // vanished with no trace and the student was told nothing. Say it
    // loudly -- the check-in genuinely did not happen.
    Serial.println("[POST] SKIPPED: no WiFi. This tap was NOT recorded.");
    return;
  }

  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  http.begin(client, CHECKIN_URL);
  http.addHeader("Content-Type", "application/json");
  // Terminal identity. The submit endpoint is unauthenticated by design
  // (the ESP32 has no login session), which previously meant ANY client
  // that could reach the URL could post a beacon. These headers let the
  // server at least attribute and gate the request.
  http.addHeader("X-Terminal-Id", TERMINAL_ID);
  http.addHeader("X-Terminal-Secret", TERMINAL_SECRET);

  String payload = "{\"beacon_token\":\"" + token + "\"}";

  Serial.println("[POST] Submitting beacon to /api/v1/student/checkin");
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

  if (httpResponseCode < 200 || httpResponseCode >= 300) {
    Serial.println("[POST] REJECTED -- check backend logs; token may have expired in transit");
  }

  http.end();
}

// ---------------- Setup / loop ----------------

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("[BOOT] SUAAMS HCE terminal starting...");

  Wire.begin(SDA_PIN, SCL_PIN);

  // 100kHz. The bring-up sketch (PN532_DetectTest.ino) sets this and notes
  // it as a knob to turn when the hit rate is poor, but this sketch never
  // did -- so it has been running the I2C bus at the Wire default (usually
  // 400kHz) the whole time. The PN532 is the slower device on the bus, so
  // the faster clock buys nothing and can drop bytes. Free change, strong
  // prior that it's part of the intermittent read failures.
  Wire.setClock(100000);

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

  connectWifi();
  Serial.printf("[BOOT] Terminal %s ready, waiting for taps...\n", TERMINAL_ID);
}

void loop() {
  // Never block on connectivity -- the NFC scan must keep running.
  maintainWifi();

  if (millis() - lastAttemptEnd < READ_COOLDOWN_MS) {
    delay(1);
    return;
  }

  // inListPassiveTarget() is the right call for an Android HCE phone: a
  // phone is an ISO14443-4 Type 4 tag with a random CL_RANDOM UID, not a
  // MIFARE target. (The bring-up sketch used
  // readPassiveTargetID(PN532_MIFARE_ISO14443A), which is a different --
  // and for HCE, less appropriate -- path; a "phone never detected"
  // result measured that way should be re-confirmed here.)
  if (!nfc.inListPassiveTarget()) {
    // Small delay so an idle terminal isn't hammering I2C at full speed.
    delay(1);
    return;
  }

  Serial.println("[TAP] Target detected, reading beacon...");
  unsigned long exchangeStart = millis();

  String token = "";
  bool gotToken = readBeacon(token);

  unsigned long exchangeDuration = millis() - exchangeStart;
  Serial.print("[TAP] Exchange finished in ");
  Serial.print(exchangeDuration);
  Serial.println("ms");

  if (gotToken && token.length() > 0) {
    submitBeaconToken(token);
  }

  lastAttemptEnd = millis();
}
