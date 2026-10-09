/*
  SUAAMS HCE Check-In Terminal
  ESP32 + PN532: reads the short-lived check-in beacon an Android phone
  broadcasts over NFC HCE and submits it to Flask. Also broadcasts a
  rotating Bluetooth code for phones that can't tap in (see the "Bluetooth
  check-in beacon" section below).

  Build settings (Arduino IDE):
    - Library Manager: install "NimBLE-Arduino" (2.x).
    - Tools > Partition Scheme > "Huge APP (3MB No OTA)". BLE + Wi-Fi +
      HTTPS no longer fit the default 1.2MB app partition.

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
#include <Preferences.h>
#include <time.h>
#include <NimBLEDevice.h>     // Library Manager: "NimBLE-Arduino" (2.x)
#include "mbedtls/md.h"       // HMAC-SHA256, built into the ESP32 core

#include "secrets.h"  // WiFi + terminal credentials. NOT in git.

// Server certificate verification (useVerifiedTls below) relies on the CA
// bundle built into arduino-esp32 3.x. On a 2.x core this would fail to
// compile with a confusing error, so say what's wrong instead.
#if !defined(ESP_ARDUINO_VERSION_MAJOR) || ESP_ARDUINO_VERSION_MAJOR < 3
#error "SUAAMS_HCE needs the esp32 board package 3.x (Boards Manager) for its built-in CA bundle."
#endif

// Older secrets.h files predate Bluetooth check-in. Fail the build with
// instructions rather than silently running without it.
#if !defined(BLE_BEACON_SECRET) || !defined(BLE_TERMINAL_NUMBER)
#error "secrets.h is missing BLE_BEACON_SECRET / BLE_TERMINAL_NUMBER -- copy them from secrets.h.example (use \"\" for the secret to keep Bluetooth off)."
#endif

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

// Transport-level retry for the POST. HTTPClient returns -1 when the
// connection or TLS handshake fails outright, which a marginal WiFi link
// produces regularly enough to lose real taps. Safe to retry because the
// submit endpoint is idempotent -- the same beacon replays as "Attendance
// already marked" rather than double-recording.
const uint8_t POST_ATTEMPTS = 2;

// Socket/TLS timeout. The beacon expires 10s after it was minted on the
// phone, and by the time a request reaches the terminal that budget is
// already partly spent. A 15s timeout therefore just meant holding the
// radio field for 15s to be told "expired" -- in the field log, attempts
// took 16.8s and 20.8s before giving up with no response at all. 6s is
// still comfortably above a warm TLS round-trip (a few hundred ms) and
// above the ~5s the pre-flight ping can cost on a genuinely cold dyno, so
// a cold start still gets its chance -- but a hopeless request now fails
// fast and lands in the offline backlog for a lecturer to review instead
// of blocking the next student's tap.
const uint16_t HTTP_TIMEOUT_MS = 6000;

// ---- Keep-warm ping -------------------------------------------------------
// A Render free-tier dyno spins down after a period without traffic, and
// the next request pays the full boot cost. Measured on this project's
// deployment: 8.5s cold (beacon rejected), 5.0-5.3s barely-warm (accepted
// by luck). The beacon acceptance window is 10s, so a cold backend means the
// student's tap is silently lost -- the app reports "could not confirm" and
// the record never appears.
//
// So the terminal keeps the backend awake itself, rather than relying on an
// external uptime service: it is already powered and networked at the
// venue, needs no account or third-party dependency, and can't be
// forgotten when the demo moves somewhere new.
const unsigned long WARM_PING_INTERVAL_MS = 4UL * 60UL * 1000UL;  // 4 minutes
const uint16_t WARM_PING_TIMEOUT_MS = 5000;

// How long a successful /healthz ping is trusted to mean "the next request
// will be fast". Sits inside the 4-minute idle ping interval on purpose:
// during an active demo the pre-flight check in ensureBackendWarmForPost()
// leans on this, and 60s keeps it re-arming the backend for a burst of
// taps without re-pinging on every single one.
const unsigned long WARM_CONFIRMED_MS = 60UL * 1000UL;
unsigned long lastWarmPing = 0;

// When the last /healthz ping succeeded. Reported alongside every tap so a
// slow POST during a demo can be attributed to a cold start rather than
// guessed at.
unsigned long lastWarmPingOk = 0;

// ---- Offline backlog queue -----------------------------------------------
// A beacon is only valid for a few seconds, so a tap captured while this
// terminal can't reach the backend has ALWAYS expired by the time it syncs.
// The server therefore will not credit it -- by design. What it does with
// it is record PROVENANCE for a lecturer to review: a genuine tap by a
// genuine student, read at a real terminal, at a known time.
//
// The capture time isn't sent from here because the terminal has no RTC
// and cannot know wall-clock time while disconnected. The server derives it
// from the beacon's own expiry field instead, so the only clock in the
// path is the server's.
//
// Bounded on purpose: this is a short buffer for a transient outage, not an
// archive. Once full, the OLDEST entry is dropped, because the most recent
// captures are the ones a lecturer is most likely to be reconciling.
const uint8_t MAX_OFFLINE_QUEUE = 16;

// How often to retry a failed flush. Short enough that a brief outage is
// recovered from promptly, long enough not to retry-hammer a backend that
// is genuinely down.
const unsigned long BACKLOG_FLUSH_INTERVAL_MS = 30UL * 1000UL;
unsigned long lastBacklogFlushAttempt = 0;

Preferences prefs;
String g_backlog = "";  // newline-separated 32-char beacons

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

// ---------------- Bluetooth check-in beacon ----------------
// The fallback for phones that can't tap in by NFC (iPhones, Android phones
// without NFC). Instead of reading a phone, the terminal BROADCASTS a code
// that rotates every 5 seconds; the app hears it and posts it to the
// server itself. Hearing a current code is the proof of presence. The
// format must match SUAAMS/ble_beacon.py byte for byte:
//
//   payload = terminal(2B BE) || slot(4B BE) || code(8B)        14 bytes
//   slot    = unix_time / 5
//   code    = HMAC-SHA256(BLE_BEACON_SECRET,
//                         "SUAAMS-BLE" || terminal || slot)[:8]
//
// It runs alongside the NFC loop, not instead of it: NimBLE advertises from
// its own task, and loop() only swaps in a new code when the slot changes.
//
// The terminal needs real wall-clock time for this (the NFC path never did),
// so it syncs over NTP. Until the first sync it broadcasts NOTHING -- a code
// built from a wrong clock would only be rejected, and silence is easier to
// diagnose than codes that never work.

// 0xFFFF is Bluetooth SIG's reserved "no company / testing" ID. The app
// filters on it. A commercial build would register its own.
const uint16_t BLE_COMPANY_ID = 0xFFFF;
const uint32_t BLE_SLOT_SECONDS = 5;          // must match SLOT_SECONDS
const uint8_t  BLE_PAYLOAD_LEN = 14;
const uint8_t  BLE_CODE_LEN = 8;
const char     BLE_DOMAIN[] = "SUAAMS-BLE";   // must match _DOMAIN

// 160 x 0.625ms = 100ms between advertisements. Mains-powered, so spend
// the airtime: a phone scanning for a few seconds hears it many times.
const uint16_t BLE_ADV_INTERVAL = 160;

// Anything before this is the ESP32's power-on epoch (1970), i.e. NTP
// hasn't answered yet. Nov 2023 is safely before any real deployment.
const time_t BLE_MIN_VALID_TIME = 1700000000;

// Known-answer vector, identical to REFERENCE_* in tests/test_ble_beacon.py.
// Checked at boot; on mismatch the terminal refuses to broadcast.
const char     BLE_REF_KEY[] = "suaams-ble-reference-key";
const uint16_t BLE_REF_TERMINAL = 1;
const uint32_t BLE_REF_SLOT = 352000000UL;
const uint8_t  BLE_REF_PAYLOAD[BLE_PAYLOAD_LEN] = {
  0x00, 0x01, 0x14, 0xFB, 0x18, 0x00,
  0xD7, 0xCE, 0x23, 0x37, 0x4F, 0xF4, 0xCC, 0xCB
};

bool bleEnabled = false;        // secret set, self-test passed, BLE up
bool bleAdvertising = false;
uint32_t bleCurrentSlot = 0;    // slot currently on air (0 = none yet)
bool bleWaitingLogged = false;
NimBLEAdvertising* bleAdv = nullptr;

// How often to log free memory. Wi-Fi + HTTPS + BLE together is tight on a
// classic ESP32; the low-water mark after real taps is the number to watch.
const unsigned long HEAP_LOG_INTERVAL_MS = 60UL * 1000UL;
unsigned long lastHeapLog = 0;

// Builds the 14-byte payload for one slot. Returns false if HMAC failed.
bool bleBuildPayload(const uint8_t* key, size_t keyLen, uint16_t terminal,
                     uint32_t slot, uint8_t out[BLE_PAYLOAD_LEN]) {
  out[0] = terminal >> 8;
  out[1] = terminal & 0xFF;
  out[2] = slot >> 24;
  out[3] = (slot >> 16) & 0xFF;
  out[4] = (slot >> 8) & 0xFF;
  out[5] = slot & 0xFF;

  // HMAC input: domain prefix, then the same 6 bytes just written.
  const size_t domainLen = sizeof(BLE_DOMAIN) - 1;  // no trailing NUL
  uint8_t message[sizeof(BLE_DOMAIN) - 1 + 6];
  memcpy(message, BLE_DOMAIN, domainLen);
  memcpy(message + domainLen, out, 6);

  uint8_t digest[32];
  const mbedtls_md_info_t* sha256 = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  if (mbedtls_md_hmac(sha256, key, keyLen, message, sizeof(message), digest) != 0) {
    return false;
  }
  memcpy(out + 6, digest, BLE_CODE_LEN);
  return true;
}

// Proves this firmware computes exactly what the server verifies, before
// any phone is involved. A mismatch here means every Bluetooth check-in
// would fail, so it's treated as fatal for BLE (NFC carries on).
bool bleSelfTest() {
  uint8_t payload[BLE_PAYLOAD_LEN];
  bool ok = bleBuildPayload((const uint8_t*)BLE_REF_KEY, sizeof(BLE_REF_KEY) - 1,
                            BLE_REF_TERMINAL, BLE_REF_SLOT, payload)
            && memcmp(payload, BLE_REF_PAYLOAD, BLE_PAYLOAD_LEN) == 0;
  printHexDump(ok ? "[BLE] Self-test PASS" : "[BLE] Self-test FAIL, got",
               payload, BLE_PAYLOAD_LEN);
  return ok;
}

void bleSetup() {
  if (strlen(BLE_BEACON_SECRET) == 0) {
    Serial.println("[BLE] BLE_BEACON_SECRET is empty -- Bluetooth check-in OFF (NFC unaffected)");
    return;
  }
  if (!bleSelfTest()) {
    Serial.println("[BLE] Refusing to broadcast: payload does not match the server's format");
    return;
  }

  Serial.printf("[HEAP] before BLE: free=%u\n", ESP.getFreeHeap());
  NimBLEDevice::init("SUAAMS");
  bleAdv = NimBLEDevice::getAdvertising();
  // Non-connectable: phones only ever listen. Nothing can open a
  // connection to the terminal, so there is no GATT surface to attack.
  bleAdv->setConnectableMode(BLE_GAP_CONN_MODE_NON);
  bleAdv->setMinInterval(BLE_ADV_INTERVAL);
  bleAdv->setMaxInterval(BLE_ADV_INTERVAL);
  Serial.printf("[HEAP] after BLE:  free=%u\n", ESP.getFreeHeap());

  bleEnabled = true;
  Serial.printf("[BLE] Ready as terminal %u; waiting for NTP before broadcasting\n",
                (unsigned)BLE_TERMINAL_NUMBER);
}

// Called every pass through loop(). Cheap unless the slot has changed.
void bleUpdate() {
  if (!bleEnabled) return;

  time_t now = time(nullptr);
  if (now < BLE_MIN_VALID_TIME) {
    if (!bleWaitingLogged) {
      Serial.println("[BLE] No NTP time yet -- not broadcasting");
      bleWaitingLogged = true;
    }
    return;
  }

  uint32_t slot = (uint32_t)(now / BLE_SLOT_SECONDS);
  if (slot == bleCurrentSlot) return;

  uint8_t payload[BLE_PAYLOAD_LEN];
  if (!bleBuildPayload((const uint8_t*)BLE_BEACON_SECRET, strlen(BLE_BEACON_SECRET),
                       BLE_TERMINAL_NUMBER, slot, payload)) {
    Serial.println("[BLE] HMAC failed -- skipping this slot");
    return;
  }

  // Manufacturer data = company ID (little-endian, per the BLE spec) then
  // our 14 bytes. With flags and the short name this is 29 of the 31
  // bytes a legacy advertisement allows.
  uint8_t mfg[2 + BLE_PAYLOAD_LEN];
  mfg[0] = BLE_COMPANY_ID & 0xFF;
  mfg[1] = BLE_COMPANY_ID >> 8;
  memcpy(mfg + 2, payload, BLE_PAYLOAD_LEN);

  NimBLEAdvertisementData data;
  data.setFlags(BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP);
  data.setManufacturerData(mfg, sizeof(mfg));
  data.setName("SUAAMS");

  // Stop, swap, restart: a gap of a few ms, once every 5 seconds.
  if (bleAdvertising) bleAdv->stop();
  bleAdv->setAdvertisementData(data);
  bleAdvertising = bleAdv->start();

  if (bleCurrentSlot == 0) {
    Serial.println("[BLE] NTP time acquired -- broadcasting");
  }
  bleCurrentSlot = slot;
  // One line per rotation. Copy the hex into `python ble_beacon.py <hex>`
  // on the server side to confirm the two agree.
  printHexDump(bleAdvertising ? "[BLE] Broadcasting" : "[BLE] START FAILED for",
               payload, BLE_PAYLOAD_LEN);
}

void logHeapPeriodically() {
  if (millis() - lastHeapLog < HEAP_LOG_INTERVAL_MS) return;
  lastHeapLog = millis();
  Serial.printf("[HEAP] free=%u lowest-ever=%u\n", ESP.getFreeHeap(), ESP.getMinFreeHeap());
}

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

// ---- Offline backlog queue ------------------------------------------------
// Stored in NVS (ESP32's key/value flash store) so captures survive both a
// power cycle and a reboot. A tap taken during a power cut is exactly the
// one you least want to lose.

uint8_t backlogCount() {
  if (g_backlog.length() == 0) return 0;
  uint8_t n = 1;
  for (unsigned int i = 0; i < g_backlog.length(); i++) {
    if (g_backlog[i] == '\n') n++;
  }
  return n;
}

void loadBacklog() {
  prefs.begin("suaams", true);
  g_backlog = prefs.getString("backlog", "");
  prefs.end();
  Serial.print("[QUEUE] Loaded ");
  Serial.print(backlogCount());
  Serial.print(" pending capture(s) from flash");
  Serial.println();
}

void saveBacklog() {
  prefs.begin("suaams", false);
  prefs.putString("backlog", g_backlog);
  prefs.end();
}

void appendToBacklog(const String &token) {
  if (token.length() == 0) return;

  // Drop the oldest entry when full. Trim the first line and its newline.
  if (backlogCount() >= MAX_OFFLINE_QUEUE) {
    int firstNewline = g_backlog.indexOf('\n');
    if (firstNewline >= 0) {
      g_backlog = g_backlog.substring(firstNewline + 1);
    } else {
      g_backlog = "";
    }
    Serial.print("[QUEUE] Full at ");
    Serial.print(MAX_OFFLINE_QUEUE);
    Serial.println(" -- dropped oldest capture");
  }

  if (g_backlog.length() > 0) g_backlog += '\n';
  g_backlog += token;
  saveBacklog();

  Serial.print("[QUEUE] Queued capture offline (");
  Serial.print(backlogCount());
  Serial.print("/");
  Serial.print(MAX_OFFLINE_QUEUE);
  Serial.println(") -- will NOT become attendance, logged for review");
}

// ---------------- TLS ----------------
// Every HTTPS request used to call client.setInsecure(). That encrypts the
// connection but never checks WHO is on the other end: anyone on the venue
// Wi-Fi could answer as the backend with their own certificate, and the
// terminal would hand them X-Terminal-Secret -- the one credential that
// proves a tap happened at a real door. With it, a student could submit
// their own beacon from anywhere.
//
// Now the server's certificate must chain to a public root CA in the
// core's built-in bundle (Mozilla's list), and must be issued for the
// URL's hostname. Deliberately the whole bundle rather than one pinned
// root: Render issues from Google Trust Services today (WE1 -> GTS Root R4,
// checked 2026-10-09) and also uses Let's Encrypt, and this terminal has no
// OTA -- a pinned root Render later moved away from would silently break
// every terminal until each one was opened and reflashed. The bundle also
// loads only the matching root per handshake, which matters on a heap
// already squeezed by Wi-Fi + BLE.
//
// Not checked: certificate expiry dates. This core is built without
// MBEDTLS_HAVE_TIME_DATE, so verification doesn't depend on the clock, and
// an unsynced clock at boot can't break check-in. The chain and hostname
// checks are what stop an impostor.
//
// A rejected certificate shows up as an ordinary transport failure (HTTP
// -1), so the tap falls through to the offline backlog instead of being
// lost -- it fails closed, and logTlsError() says why.
void useVerifiedTls(WiFiClientSecure& client) {
  client.useBuiltinCACertBundle();
}

// Explains a -1. Without this, "certificate rejected" and "Wi-Fi dropped"
// print identically, and a misconfigured terminal would look merely
// offline while quietly queuing every tap.
void logTlsError(WiFiClientSecure& client, const char* tag) {
  char buf[100];
  int err = client.lastError(buf, sizeof(buf));
  if (err != 0) {
    Serial.printf("[%s] TLS error %d: %s\n", tag, err, buf);
  }
}

// POSTs the queue and clears it on success.
//
// Clears only when the server actually accepted the batch. A transport
// failure leaves the queue intact so nothing is lost, and a 4xx/5xx clears
// it too: the server gave a real answer, and re-sending an answer it has
// already given us would just wedge the same entries in the queue forever.
bool flushBacklog() {
  if (g_backlog.length() == 0) return true;
  if (WiFi.status() != WL_CONNECTED) return false;

  String records;
  records.reserve(g_backlog.length() + 64);
  uint8_t count = 0;
  int start = 0;
  while (true) {
    int nl = g_backlog.indexOf('\n', start);
    String line = (nl >= 0) ? g_backlog.substring(start, nl) : g_backlog.substring(start);
    if (line.length() > 0) {
      if (count > 0) records += ',';
      records += "{\"beacon_token\":\"" + line + "\"}";
      count++;
    }
    if (nl < 0) break;
    start = nl + 1;
  }
  if (count == 0) { g_backlog = ""; saveBacklog(); return true; }

  String payload = "{\"records\":[" + records + "]}";

  WiFiClientSecure client;
  useVerifiedTls(client);  // was setInsecure(); see the TLS section above

  HTTPClient http;
  http.begin(client, BACKLOG_URL);
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Terminal-Id", TERMINAL_ID);
  http.addHeader("X-Terminal-Secret", TERMINAL_SECRET);

  Serial.print("[QUEUE] Flushing ");
  Serial.print(count);
  Serial.print(" capture(s) to backlog endpoint...");
  int code = http.POST(payload);
  String body = http.getString();
  http.end();

  if (code == 200) {
    g_backlog = "";
    saveBacklog();
    Serial.println(" accepted, queue cleared");
    return true;
  }

  if (code == -1) {
    Serial.println(" no response -- queue RETAINED, will retry later");
    logTlsError(client, "QUEUE");
  } else {
    // Real answer from a reachable server. Keeping these would wedge the
    // queue permanently, so drop them -- the server has the record either way.
    g_backlog = "";
    saveBacklog();
    Serial.print(" server returned ");
    Serial.print(code);
    Serial.print(" -- queue cleared, server has the record: ");
    Serial.println(body);
  }
  return false;
}

// Pings /healthz on a timer to stop the backend spinning down.
//
// Only ever called when the NFC field is EMPTY (see loop()), so it can never
// steal scan time from a student mid-tap. The ping is a synchronous TLS
// request costing a few hundred ms, which is a fine trade for a field with
// nothing in it and a real problem when it has a student in it.
void maybeKeepBackendWarm(bool force = false) {
  if (!force && millis() - lastWarmPing < WARM_PING_INTERVAL_MS) {
    return;
  }
  lastWarmPing = millis();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WARM] Skipped: no WiFi");
    return;
  }

  WiFiClientSecure client;
  useVerifiedTls(client);  // was setInsecure(); see the TLS section above

  HTTPClient http;
  http.begin(client, HEALTHZ_URL);
  http.setTimeout(WARM_PING_TIMEOUT_MS);

  unsigned long t0 = millis();
  int code = http.GET();
  unsigned long dur = millis() - t0;

  http.end();

  if (code == 200) {
    lastWarmPingOk = millis();
    Serial.print("[WARM] /healthz 200 in ");
    Serial.print(dur);
    Serial.println("ms -- backend warm");
  } else {
    // Not fatal. The next attempt, and the next tap, will just be slower.
    Serial.print("[WARM] /healthz returned ");
    Serial.print(code);
    Serial.print(" in ");
    Serial.print(dur);
    Serial.println("ms -- backend may be cold");
    // The boot-time ping is the first HTTPS call, so a certificate problem
    // shows up here before any student taps.
    if (code == -1) logTlsError(client, "WARM");
  }
}

// Runs just before a check-in POST, once the beacon is already read.
//
// The beacon TTL is 10 seconds, and it is spent from MINT time -- the clock
// started on the phone before the student ever reached the terminal. By the
// time the radio exchange finishes, some of that budget is already gone, so
// the POST itself has very little slack. On a Render free-tier dyno that
// spun down, the TLS handshake alone measured 8.5s, which is a guaranteed
// rejection no matter how correct the rest of the flow is.
//
// Doing the warm-up HERE, after the radio read and before the POST, means:
//
//   - The RF exchange is never delayed. The NFC read is the one part with
//     a hard real-time budget (the phone's HCE response is time-sensitive
//     and the beacon is expiring), so it happens first and uninterrupted.
//   - The cold-start cost, which the POST was going to pay anyway, is paid
//     here instead. The POST that follows then finds a warm dyno and
//     completes in a few hundred ms -- inside the window.
//
// Previously this only ever ran when the field was EMPTY (see loop()), so
// with a phone resting against the terminal it never fired at all: every
// tap in the field log shows "[WARM] No successful /healthz ping yet this
// boot" followed by an 8-20 second POST. The phone being in the field is
// precisely when warming matters most.
void ensureBackendWarmForPost() {
  // Already confirmed warm recently -- a POST would be fast regardless, and
  // spending a few hundred ms on a redundant ping here delays the one
  // request that actually matters.
  if (lastWarmPingOk != 0 &&
      (millis() - lastWarmPingOk) < WARM_CONFIRMED_MS) {
    return;
  }
  Serial.println("[WARM] Pre-flight ping before POST (backend not confirmed warm)");
  maybeKeepBackendWarm(true);
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
    // No network at all. This is exactly the case the offline queue exists
    // for -- queue it rather than dropping it, so a lecturer can at least
    // see a genuine tap happened even though it can't become attendance.
    Serial.println("[POST] No WiFi -- queuing capture for later sync");
    appendToBacklog(token);
    return;
  }

  String payload = "{\"beacon_token\":\"" + token + "\"}";

  // Pay the cold-start cost HERE rather than letting the POST below discover
  // it. The beacon is already read, so nothing on the radio side is delayed;
  // the POST then runs against a warm dyno and has a real chance of landing
  // inside the acceptance window. See ensureBackendWarmForPost() for why this
  // sits here and not in loop().
  ensureBackendWarmForPost();

  // Report how long since the backend last confirmed itself warm. If a POST
  // is about to run slow, this line tells you whether it's a cold start or
  // something else -- which is the difference between "wait and retry" and
  // "the network is bad".
  if (lastWarmPingOk == 0) {
    Serial.println("[WARM] No successful /healthz ping yet this boot");
  } else {
    Serial.print("[WARM] Last successful ping was ");
    Serial.print((millis() - lastWarmPingOk) / 1000);
    Serial.println("s ago");
  }

  // Retry the transport-level failures. A single attempt is fragile here:
  // HTTPClient returns -1 (not an HTTP status -- no response at all) when
  // connect() or the TLS handshake fails, which on a marginal WiFi link
  // happens often enough to lose real taps. Retrying is only safe because
  // the submit endpoint is idempotent: replaying the same beacon returns
  // "Attendance already marked" rather than double-recording.
  //
  // Deliberately NOT retried on a 4xx/5xx -- those are real answers from a
  // reachable server (expired token, unauthorized terminal), and repeating
  // them just wastes the student's remaining window.
  for (uint8_t attempt = 1; attempt <= POST_ATTEMPTS; attempt++) {
    WiFiClientSecure client;
    useVerifiedTls(client);  // was setInsecure(); see the TLS section above

    HTTPClient http;
    http.begin(client, CHECKIN_URL);
    http.setTimeout(HTTP_TIMEOUT_MS);
    http.addHeader("Content-Type", "application/json");
    // Terminal identity. The submit endpoint is unauthenticated by design
    // (the ESP32 has no login session), which previously meant ANY client
    // that could reach the URL could post a beacon. These headers let the
    // server at least attribute and gate the request.
    http.addHeader("X-Terminal-Id", TERMINAL_ID);
    http.addHeader("X-Terminal-Secret", TERMINAL_SECRET);

    Serial.print("[POST] Submitting beacon (attempt ");
    Serial.print(attempt);
    Serial.print(" of ");
    Serial.print(POST_ATTEMPTS);
    Serial.println(")...");

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

    // -1 means no response at all: connection refused, DNS failure, or a
    // TLS handshake that didn't complete. Worth another go, and if every
    // attempt fails that is an outage from our point of view, so the
    // capture gets queued for the backlog endpoint.
    if (httpResponseCode == -1) {
      Serial.println("[POST] No response (transport failure) -- will retry");
      logTlsError(client, "POST");
      // Back off briefly so we don't hammer a link that's already struggling.
      delay(1500);
      continue;
    }

    if (httpResponseCode < 200 || httpResponseCode >= 300) {
      Serial.println("[POST] REJECTED by server -- not retrying. If this was 401,");
      Serial.println("[POST] the beacon likely expired before the server saw it.");
      Serial.println("[POST] Check: is the Render dyno warm? A cold start costs 5-9s,");
      Serial.println("[POST] and the acceptance window is only 10s.");
    }
    // Any real HTTP status means the backend WAS reachable, so this isn't an
    // outage and must not be queued -- the server has given its answer.
    return;
  }

  // Every attempt was a transport failure: the backend was unreachable, so
  // treat this as offline rather than as a lost tap.
  Serial.println("[POST] All attempts failed at the transport layer -- queuing capture");
  appendToBacklog(token);
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

  // Restore any captures queued before the last power cycle, BEFORE going
  // live, so taps that happened during an outage aren't sitting in flash
  // unaccounted for.
  loadBacklog();

  connectWifi();
  // Wall-clock time for the Bluetooth code (UTC; no timezone needed, the
  // slot is plain unix time). Safe to call even if Wi-Fi isn't up yet: the
  // SNTP client keeps retrying in the background and re-syncs about hourly,
  // and the ESP32 keeps counting between syncs, so a Wi-Fi drop doesn't
  // stop broadcasting.
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  // Warm the backend as the LAST thing at boot. This used to wait out a
  // full WARM_PING_INTERVAL_MS before the first ping ever fired, because
  // lastWarmPing starts at 0 and millis() starts near 0 -- so the very
  // first tap after power-on always paid a full cold start, which on a
  // free-tier dyno (measured 8.5s here) is longer than the beacon's entire
  // 10s window. Forcing the ping here means the backend is already awake
  // before the first student walks up.
  maybeKeepBackendWarm(true);
  // After the warm ping on purpose: that first TLS handshake is the
  // biggest heap spike, so the before/after BLE numbers are measured
  // against a heap that has already been through it.
  bleSetup();
  Serial.printf("[BOOT] Terminal %s ready, waiting for taps...\n", TERMINAL_ID);
}

void loop() {
  // Never block on connectivity -- the NFC scan must keep running.
  maintainWifi();

  // Rotate the Bluetooth code when its 5s slot ends. Runs every pass, but
  // returns at once unless the slot changed. inListPassiveTarget() below
  // can block for up to about a second, so a rotation may land late by
  // that much -- harmless, since the server also accepts the previous slot.
  bleUpdate();
  logHeapPeriodically();

  // inListPassiveTarget() is the right call for an Android HCE phone: a
  // phone is an ISO14443-4 Type 4 tag, not a MIFARE target. (The bring-up
  // sketch originally measured with readPassiveTargetID(PN532_MIFARE_ISO14443A),
  // which does not detect HCE phones at all -- a real bench run confirmed
  // it reported card=n on every successful tap.)
  bool targetInField = nfc.inListPassiveTarget();

  // Keep the backend warm, but ONLY when nothing is in the field. A warm
  // ping is a synchronous TLS request costing a few hundred ms; doing that
  // while a student is mid-tap risks missing their read entirely. With an
  // empty field there's nothing to lose.
  if (!targetInField) {
    maybeKeepBackendWarm();

    // Push any offline captures now that the backend is answering. Only
    // attempted on an empty field, for the same reason as the warm ping: a
    // flush is a synchronous TLS request and must never delay a real tap.
    if (backlogCount() > 0) {
      unsigned long age = millis() - lastBacklogFlushAttempt;
      if (age > BACKLOG_FLUSH_INTERVAL_MS) {
        lastBacklogFlushAttempt = millis();
        flushBacklog();
      }
    }
  }

  if (millis() - lastAttemptEnd < READ_COOLDOWN_MS) {
    delay(1);
    return;
  }

  if (!targetInField) {
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
