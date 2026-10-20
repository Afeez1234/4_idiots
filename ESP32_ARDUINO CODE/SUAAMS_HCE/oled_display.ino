// ---------------- OLED status screen ----------------
// A 0.96" SSD1306 (128x64, I2C) at the door, so a student sees the result
// of their tap at the terminal instead of only on their phone.
//
// Arduino builds every .ino in this folder as one file, main sketch first,
// so this tab can read the main sketch's globals (wifiReady, bleAdvertising,
// backlogCount()...) and the main sketch calls the oledShow*() functions
// below. Those take only plain types on purpose: the Arduino builder
// generates prototypes near the top of the file, before any enum declared
// here would exist.
//
// WIRING -- its own I2C bus, not the PN532's:
//   OLED SDA -> GPIO 25, OLED SCL -> GPIO 26, VCC -> 3.3V, GND -> GND
// The PN532 bus (GPIO 21/22) runs at 100 kHz for the PN532's sake. A full
// frame is 1 KB, which at 100 kHz takes ~100 ms, and the reader can't look
// for phones meanwhile. On the second bus at 400 kHz a frame takes ~25 ms,
// and a screen fault can't touch the reader.
//
// The screen only redraws when what it shows changes, and loop() only lets
// it redraw when no phone is in the field (see oledUpdate()).
//
// It's optional hardware: if it's missing or won't start, the terminal logs
// that and works exactly as before.

#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define OLED_SDA_PIN 25
#define OLED_SCL_PIN 26
#define OLED_WIDTH 128
#define OLED_HEIGHT 64

TwoWire oledWire = TwoWire(1);
Adafruit_SSD1306 oled(OLED_WIDTH, OLED_HEIGHT, &oledWire, -1);
bool oledOk = false;

// How long a tap's result stays up before going back to the idle screen.
const unsigned long OLED_RESULT_MS = 3000;
// After this long with no taps the idle screen dims, and its content shifts
// by a pixel each minute. OLED pixels age with use, so a static bright
// "TAP PHONE" for a whole day would burn in.
const unsigned long OLED_DIM_AFTER_MS = 2UL * 60UL * 1000UL;
const unsigned long OLED_SHIFT_EVERY_MS = 60UL * 1000UL;

// The faces. Fonts here are plain ASCII, so these are drawn by hand.
const uint8_t FACE_HAPPY = 0;     // recorded
const uint8_t FACE_MEH = 1;       // already marked, saved offline
const uint8_t FACE_SAD = 2;       // rejected
const uint8_t FACE_THINKING = 3;  // waiting on the server
const uint8_t FACE_SLEEPY = 4;    // idle and dimmed

const uint8_t OLED_IDLE = 0;
const uint8_t OLED_RESULT = 1;  // a result or "checking", held for a while
uint8_t oledMode = OLED_IDLE;
unsigned long oledResultUntil = 0;
unsigned long oledLastActivity = 0;
// What the idle screen last drew, so it only redraws on a change.
uint32_t oledIdleDrawn = 0xFFFFFFFF;
// door.version the idle screen last drew (see DoorStatus in the main sketch).
uint32_t oledIdleDoorDrawn = 0xFFFFFFFF;

// Clock in the top line. The board's clock is UTC (configTime(0, 0) in the
// main sketch, which the Bluetooth code needs); campus is Africa/Lagos,
// UTC+1 all year with no daylight saving, so a fixed offset is exact. Done
// here rather than with setenv("TZ") so nothing else's time changes.
const long CAMPUS_UTC_OFFSET_S = 3600;

// Progress bar under "Checking...". While the server answers, loop() is
// stuck inside a blocking HTTPS request and can't redraw, so a small task
// on the other core animates the bar. oledLock makes sure it and loop()
// never draw at the same time; the OLED is alone on its bus, so this
// can't disturb the PN532. The bar fills over the beacon's 10-second
// acceptance window, so a cold-server wait visibly moves instead of
// looking frozen.
SemaphoreHandle_t oledLock = nullptr;
volatile unsigned long oledWaitStart = 0;  // 0 = not waiting
const unsigned long OLED_BAR_FULL_MS = 10000;
const int16_t OLED_BAR_X = 40, OLED_BAR_Y = 50, OLED_BAR_W = 84, OLED_BAR_H = 7;

void oledBarTask(void*) {
  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(150));
    if (!oledWaitStart) continue;
    xSemaphoreTake(oledLock, portMAX_DELAY);
    // Re-checked under the lock: a result may have replaced the screen
    // while we waited for it.
    if (oledWaitStart) {
      unsigned long elapsed = millis() - oledWaitStart;
      int16_t fill = elapsed >= OLED_BAR_FULL_MS
                         ? OLED_BAR_W - 2
                         : (int16_t)((OLED_BAR_W - 2) * elapsed / OLED_BAR_FULL_MS);
      oled.fillRect(OLED_BAR_X + 1, OLED_BAR_Y + 1, fill, OLED_BAR_H - 2, SSD1306_WHITE);
      oled.display();
    }
    xSemaphoreGive(oledLock);
  }
}

void oledBegin() {
  oledWire.begin(OLED_SDA_PIN, OLED_SCL_PIN, 400000);

  // Ask the bus first. oled.begin() only reports whether it could allocate
  // its frame buffer -- it never checks that a screen answered -- so on its
  // own it says "ready" with nothing wired up at all. 0x3C is the usual
  // address; some boards are strapped to 0x3D.
  uint8_t addr = 0;
  for (uint8_t candidate : {0x3C, 0x3D}) {
    oledWire.beginTransmission(candidate);
    if (oledWire.endTransmission() == 0) { addr = candidate; break; }
  }
  if (!addr) {
    Serial.println("[OLED] No screen answered on GPIO 25 (SDA) / 26 (SCL) -- carrying on without it."
                   " Run OLED_Test to find it.");
    return;
  }

  oledOk = oled.begin(SSD1306_SWITCHCAPVCC, addr);
  if (!oledOk) {
    Serial.println("[OLED] Screen found but couldn't allocate its buffer -- carrying on without it");
    return;
  }
  Serial.printf("[OLED] Screen ready at 0x%02X\n", addr);
  oledLastActivity = millis();
  // A long network name or terminal ID is cut off at the edge rather than
  // wrapping onto the line below it.
  oled.setTextWrap(false);

  // Core 0, beside the Wi-Fi stack; loop() runs on core 1. The task sleeps
  // unless "Checking..." is up, so it costs nothing the rest of the time.
  oledLock = xSemaphoreCreateMutex();
  xTaskCreatePinnedToCore(oledBarTask, "oledBar", 3072, nullptr, 1, nullptr, 0);
}

// Idle brightness. Not the library's dim(): that sets contrast 0, which on
// many of these panels looks fully OFF in a lit room -- so the dimmed idle
// screen read as "the screen died". 0x30 of 0xFF is still clearly visible
// but ages the pixels far more slowly than full brightness.
const uint8_t OLED_CONTRAST_FULL = 0xCF;  // the library's own default
const uint8_t OLED_CONTRAST_IDLE = 0x30;

void oledSetDimmed(bool dimmed) {
  oled.ssd1306_command(SSD1306_SETCONTRAST);
  oled.ssd1306_command(dimmed ? OLED_CONTRAST_IDLE : OLED_CONTRAST_FULL);
}

void oledDrawFace(int16_t cx, int16_t cy, uint8_t face) {
  const int16_t r = 14;
  oled.drawCircle(cx, cy, r, SSD1306_WHITE);

  // Eyes
  if (face == FACE_SLEEPY) {
    oled.drawFastHLine(cx - 8, cy - 4, 5, SSD1306_WHITE);
    oled.drawFastHLine(cx + 4, cy - 4, 5, SSD1306_WHITE);
  } else if (face == FACE_THINKING) {
    // Looking up and to the side.
    oled.fillCircle(cx - 4, cy - 6, 2, SSD1306_WHITE);
    oled.fillCircle(cx + 6, cy - 6, 2, SSD1306_WHITE);
  } else {
    oled.fillCircle(cx - 5, cy - 4, 2, SSD1306_WHITE);
    oled.fillCircle(cx + 5, cy - 4, 2, SSD1306_WHITE);
  }

  // Mouth. drawCircleHelper draws one quarter of a circle per bit:
  // 0x4 | 0x8 is the bottom half (a smile), 0x1 | 0x2 the top half (a frown).
  switch (face) {
    case FACE_HAPPY:
      oled.drawCircleHelper(cx, cy + 2, 7, 0x4 | 0x8, SSD1306_WHITE);
      break;
    case FACE_SAD:
      oled.drawCircleHelper(cx, cy + 11, 7, 0x1 | 0x2, SSD1306_WHITE);
      break;
    case FACE_THINKING:
      oled.drawLine(cx - 4, cy + 7, cx + 5, cy + 5, SSD1306_WHITE);
      break;
    case FACE_SLEEPY:
      oled.drawCircle(cx, cy + 6, 2, SSD1306_WHITE);  // a small "o"
      // "zZ" above the right of the head, clear of the big word at x = 40.
      oled.setTextSize(1);
      oled.setCursor(cx + 9, cy - r - 2);
      oled.print("z");
      oled.setCursor(cx + 14, cy - r - 9);
      oled.print("Z");
      break;
    default:  // FACE_MEH
      oled.drawFastHLine(cx - 6, cy + 6, 13, SSD1306_WHITE);
      break;
  }
}

// Campus wall-clock minutes since midnight, or -1 before the first time
// sync (the clock starts at 1970 and reads as nonsense until then).
int16_t campusMinuteOfDay() {
  time_t now = time(nullptr);
  if (now < 1700000000) return -1;
  now += CAMPUS_UTC_OFFSET_S;
  struct tm t;
  gmtime_r(&now, &t);
  return t.tm_hour * 60 + t.tm_min;
}

// Wi-Fi signal as 0-4 bars (0 = not connected). Thresholds are the usual
// ones: -55 dBm and up is excellent, below -75 is marginal.
uint8_t wifiBars() {
  if (!wifiReady || WiFi.status() != WL_CONNECTED) return 0;
  int32_t rssi = WiFi.RSSI();
  if (rssi >= -55) return 4;
  if (rssi >= -65) return 3;
  if (rssi >= -75) return 2;
  return 1;
}

// "Can this terminal reach the server right now?" -- what a lecturer needs
// to know before trusting that taps are landing. Yes when a /healthz ping
// or a check-in got a real answer within the last ping interval plus a
// minute of slack, and nothing has failed since. Being on Wi-Fi isn't
// enough: a hotspot out of data is on Wi-Fi.
bool serverReachable() {
  return wifiReady && networkStrikes == 0 && lastWarmPingOk != 0 &&
         millis() - lastWarmPingOk < WARM_PING_INTERVAL_MS + 60000UL;
}

// The permanent top row, for a lecturer's glance:
//   [signal bars] ON|OFF      10:42      Q:3
// ON/OFF is the server (serverReachable), not the Wi-Fi. Q is the offline
// queue: taps stored on the terminal, waiting to be uploaded for review.
void oledDrawStatusLine(int16_t dx) {
  oled.setTextSize(1);

  // Four rising bars, filled up to the signal strength; outlines only for
  // the rest, so "1 of 4" still reads as a weak signal and not as a glitch.
  uint8_t bars = wifiBars();
  for (uint8_t i = 0; i < 4; i++) {
    int16_t h = 2 + 2 * i;
    int16_t x = dx + i * 3;
    if (i < bars) {
      oled.fillRect(x, 8 - h, 2, h, SSD1306_WHITE);
    } else {
      oled.drawFastHLine(x, 7, 2, SSD1306_WHITE);  // just a stub
    }
  }
  if (bars == 0) {
    // No Wi-Fi at all: a small x over the bars.
    oled.drawLine(dx + 1, 0, dx + 9, 6, SSD1306_WHITE);
    oled.drawLine(dx + 1, 6, dx + 9, 0, SSD1306_WHITE);
  }

  oled.setCursor(dx + 15, 0);
  oled.print(serverReachable() ? "ON" : "OFF");

  int16_t minute = campusMinuteOfDay();
  char clock[6];
  if (minute < 0) {
    strcpy(clock, "--:--");
  } else {
    snprintf(clock, sizeof(clock), "%02d:%02d", minute / 60, minute % 60);
  }
  oled.setCursor((OLED_WIDTH - 6 * 5) / 2 + dx, 0);
  oled.print(clock);

  // Always shown, even at 0: "Q:0" is itself the answer to "is anything
  // stuck on this terminal?". At most "Q:100", which clears the clock.
  char right[8];
  snprintf(right, sizeof(right), "Q:%u", backlogCount());
  oled.setCursor(OLED_WIDTH - 6 * strlen(right) - 1 + dx, 0);
  oled.print(right);
  oled.drawFastHLine(0, 10, OLED_WIDTH, SSD1306_WHITE);
}

// The shared layout: status line, face on the left, a big word and up to
// two small lines on the right. The big word fits 7 characters, each small
// line about 14. Every full redraw goes through here, under oledLock, and
// says whether the progress bar should keep animating afterwards
// (`waiting`) -- set in the same locked section, so the bar task can never
// paint a bar over a screen that has just replaced "Checking...".
void oledDraw(uint8_t face, const char* title, const char* line1, const char* line2,
              int16_t dx, int16_t dy, bool dimmed, bool waiting) {
  xSemaphoreTake(oledLock, portMAX_DELAY);
  oledWaitStart = 0;
  oledSetDimmed(dimmed);
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oledDrawStatusLine(dx);
  oledDrawFace(18 + dx, 38 + dy, face);

  oled.setTextSize(2);
  oled.setCursor(40 + dx, 16 + dy);
  oled.print(title);
  oled.setTextSize(1);
  oled.setCursor(40 + dx, 38 + dy);
  oled.print(line1);
  oled.setCursor(40 + dx, 49 + dy);
  oled.print(line2);
  if (waiting) {
    oled.drawRect(OLED_BAR_X, OLED_BAR_Y, OLED_BAR_W, OLED_BAR_H, SSD1306_WHITE);
  }
  oled.display();
  if (waiting) oledWaitStart = millis() | 1;  // 0 means "not waiting"
  xSemaphoreGive(oledLock);
}

// The idle screen when the server has placed this reader in a room
// (`door`, from /terminal/status). No face: the space goes to the class.
//
//   live:   MCT 401        +1      no class:  NO CLASS
//           23 / 40 checked in                Next: MCT 405
//           ends 11:00                        at 14:00
//           TAP your phone                    (or "Nothing else today")
void oledDrawDoor(int16_t dx, int16_t dy, bool dimmed) {
  xSemaphoreTake(oledLock, portMAX_DELAY);
  oledWaitStart = 0;
  oledSetDimmed(dimmed);
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oledDrawStatusLine(dx);

  char line[24];
  if (door.live) {
    oled.setTextSize(2);
    oled.setCursor(dx, 14 + dy);
    oled.print(door.course);  // 7 characters fit; "MCT 401" is exactly 7
    oled.setTextSize(1);
    if (door.more) {
      // Another class is live in the same room: say so rather than hide it.
      snprintf(line, sizeof(line), "+%u", door.more);
      oled.setCursor(OLED_WIDTH - 6 * strlen(line) - 1 + dx, 18 + dy);
      oled.print(line);
    }
    snprintf(line, sizeof(line), "%u / %u checked in", door.present, door.enrolled);
    oled.setCursor(dx, 33 + dy);
    oled.print(line);
    if (door.ends[0]) {
      snprintf(line, sizeof(line), "ends %s", door.ends);
      oled.setCursor(dx, 43 + dy);
      oled.print(line);
    }
    oled.setCursor(dx, 55 + dy);
    oled.print("TAP your phone");
  } else {
    oled.setTextSize(2);
    oled.setCursor(dx, 14 + dy);
    oled.print("NO CLASS");
    oled.setTextSize(1);
    if (door.hasNext) {
      snprintf(line, sizeof(line), "Next: %s", door.nextCourse);
      oled.setCursor(dx, 38 + dy);
      oled.print(line);
      snprintf(line, sizeof(line), "at %s", door.nextStarts);
      oled.setCursor(dx, 49 + dy);
      oled.print(line);
    } else {
      oled.setCursor(dx, 38 + dy);
      oled.print("Nothing else today");
    }
  }
  oled.display();
  xSemaphoreGive(oledLock);
}

// A result or progress screen, held for OLED_RESULT_MS (holdMs = 0 holds
// until the next call, for "checking").
void oledShow(uint8_t face, const char* title, const char* line1, const char* line2,
              unsigned long holdMs, bool waiting = false) {
  if (!oledOk) return;
  oledDraw(face, title, line1, line2, 0, 0, false, waiting);
  oledMode = OLED_RESULT;
  oledResultUntil = holdMs ? millis() + holdMs : 0;
  oledLastActivity = millis();
  oledIdleDrawn = 0xFFFFFFFF;  // the idle screen will need a full redraw
}

// ---- Called from the main sketch ----

void oledShowBoot(const char* line) {
  oledShow(FACE_THINKING, "HELLO", line, "", 0);
}

// Shown for a few seconds at the end of boot: which terminal this is and
// which room the server has it in (else the network it joined). With
// several identical boards, it's how you tell them apart while mounting
// them -- and "Room not set" is the cue to set it on the Terminals page.
void oledShowReady() {
  char second[24];
  if (door.known) {
    if (door.room[0]) {
      snprintf(second, sizeof(second), "Room %s", door.room);
    } else {
      strcpy(second, "Room not set");
    }
  } else {
    copyField(second, sizeof(second),
              (wifiReady && wifiCurrentNetwork >= 0) ? KNOWN_NETWORKS[wifiCurrentNetwork].ssid : "no wifi yet");
  }
  oledShow(FACE_HAPPY, "READY", TERMINAL_ID, second, 4000);
}

// Ends a held screen (the boot "HELLO") and lets oledUpdate() draw idle.
void oledShowIdle() {
  oledMode = OLED_IDLE;
  oledIdleDrawn = 0xFFFFFFFF;
  oledUpdate();
}

void oledShowChecking() {
  oledShow(FACE_THINKING, "WAIT", "Checking...", "", 0, true);
}

// `firstName` may be empty ("Already marked" carries no name).
void oledShowRecorded(const char* firstName) {
  oledShow(FACE_HAPPY, "DONE", firstName[0] ? firstName : "You're in", "marked present", OLED_RESULT_MS);
}

void oledShowAlreadyMarked() {
  oledShow(FACE_MEH, "DONE", "Already", "marked", OLED_RESULT_MS);
}

void oledShowQueued() {
  oledShow(FACE_MEH, "SAVED", "No internet.", "To be reviewed", OLED_RESULT_MS);
}

void oledShowRejectionTwo(const char* line1, const char* line2) {
  oledShow(FACE_SAD, "OOPS", line1, line2, OLED_RESULT_MS);
}

// The server's answer to a check-in, as a screen. Keyed on the HTTP code
// plus a fixed word from the body where one code covers two cases, so a
// rewording of the server's messages can't change what students see.
// See submit_checkin_beacon() in SUAAMS/api/student.py for the responses.
void oledShowServerAnswer(int code, const String& body) {
  if (code >= 200 && code < 300) {
    if (body.indexOf("already") >= 0) {
      oledShowAlreadyMarked();
    } else {
      char first[15];
      firstNameFromResponse(body, first, sizeof(first));
      oledShowRecorded(first);
      if (door.live) {
        // Count it now rather than waiting up to a minute for the refresh;
        // the refresh then corrects it (Bluetooth and hand marks).
        door.present++;
        door.version++;
      } else {
        // A check-in landed while the screen said NO CLASS: a lecturer has
        // started one since the last refresh. Refresh on the next idle pass.
        lastWarmPing = 0;
      }
    }
    return;
  }

  switch (code) {
    case 401:
      // Same code for a bad terminal secret and an expired/forged code.
      if (body.indexOf("terminal") >= 0) {
        oledShowRejectionTwo("Terminal not", "set up. Admin");
      } else {
        oledShowRejectionTwo("Code expired.", "Tap again");
      }
      return;
    case 400:
      oledShowRejectionTwo("Not registered", "for this class");
      return;
    case 404:
      oledShowRejectionTwo("Not found.", "See lecturer");
      return;
    case 409:
      if (body.indexOf("wrong_room") >= 0) {
        oledShowRejectionTwo("Wrong room.", "Check class");
      } else {
        oledShowRejectionTwo("Class has", "ended");
        lastWarmPing = 0;  // the screen may still show it as live: refresh
      }
      return;
    default:
      oledShowRejectionTwo("Server error.", "Tap again");
      return;
  }
}

// Back to idle once a result has been up long enough, and keep the idle
// screen current. Cheap when nothing changed. Only call this with no phone
// in the field: a redraw takes ~25 ms.
void oledUpdate() {
  if (!oledOk) return;

  if (oledMode == OLED_RESULT) {
    if (oledResultUntil == 0 || millis() < oledResultUntil) return;
    oledMode = OLED_IDLE;
  }

  unsigned long idleFor = millis() - oledLastActivity;
  bool dimmed = idleFor > OLED_DIM_AFTER_MS;
  // Burn-in: once dimmed, nudge everything around a 3x3 grid of offsets.
  uint8_t step = dimmed ? (idleFor / OLED_SHIFT_EVERY_MS) % 9 : 4;  // 4 = centre
  int16_t dx = (step % 3) - 1;
  int16_t dy = (step / 3) - 1;

  // Everything the idle screen shows, packed, so it redraws only on change.
  uint32_t drawn = (uint32_t)wifiBars()                          // bits 0-2
                 | ((uint32_t)(serverReachable() ? 1 : 0) << 3)
                 | ((uint32_t)(dimmed ? 1 : 0) << 5)
                 | ((uint32_t)step << 6)
                 | ((uint32_t)backlogCount() << 10)
                 | ((uint32_t)(campusMinuteOfDay() + 1) << 18);  // the clock
  if (drawn == oledIdleDrawn && door.version == oledIdleDoorDrawn) return;
  oledIdleDrawn = drawn;
  oledIdleDoorDrawn = door.version;

  // The class screen once the server has placed this reader in a room;
  // until then (no answer yet, no room set, old shared secret) the plain
  // TAP screen. Bluetooth check-ins never show on either: the phone posts
  // the code to the server itself, so the terminal never learns about them
  // -- the count catches up on the next refresh.
  if (door.known && door.room[0]) {
    oledDrawDoor(dx, dy, dimmed);
  } else {
    oledDraw(dimmed ? FACE_SLEEPY : FACE_HAPPY, "TAP", "your phone", "here", dx, dy, dimmed, false);
  }
}

// The first word of the student's name from the check-in response, e.g.
// {"student": {"full_name": "Ada Okafor"}} -> "Ada". Only the first name
// goes on screen: it's public, and the next person in the queue can read
// it. Stops at a backslash too, since a JSON escape (an accented letter)
// wouldn't draw in this ASCII font anyway.
void firstNameFromResponse(const String& body, char* out, size_t outLen) {
  out[0] = '\0';
  int at = body.indexOf("\"full_name\"");
  if (at < 0) return;
  at = body.indexOf('"', body.indexOf(':', at) + 1);
  if (at < 0) return;
  size_t n = 0;
  for (int i = at + 1; i < (int)body.length() && n + 1 < outLen; i++) {
    char c = body[i];
    if (c == '"' || c == ' ' || c == '\\') break;
    out[n++] = c;
  }
  out[n] = '\0';
}
