/*
  PN532 detection-only bring-up test (ESP32, I2C).

  Purpose: isolate the RF/transport layer from everything else. No WiFi, no
  backend, no token chunking -- just "how often does the PN532 see a target,
  and does the phone's HCE service answer a SELECT". Run this with (a) a known
  NFC card/tag and (b) the phone with the SUAAMS app open, screen on and
  unlocked, and compare the hit rates.

  Reading the output:
    - card hit rate high, phone hit rate low  -> phone-side state / antenna
      alignment / HCE routing problem.
    - both low                                -> PN532 power, antenna or I2C
      transport problem (try 5V on VCC, then HSU/SPI).
    - phone detected but SELECT gives no answer -> link forms, HCE service
      isn't engaging (AID mismatch, preferred service, phone locked).
    - SELECT answers 6A88                       -> full path works; the app
      simply had no token set (expected if no check-in is active).
*/

#include <Wire.h>
#include <Adafruit_PN532.h>

#define SDA_PIN 21
#define SCL_PIN 22
#define PN532_IRQ   -1
#define PN532_RESET -1
Adafruit_PN532 nfc(PN532_IRQ, PN532_RESET);

// Same AID as apduservice.xml / SuaamsHceService.kt / SUAAMS_HCE.ino.
const uint8_t SELECT_APDU[] = {
  0x00, 0xA4, 0x04, 0x00, 0x07,
  0xF0, 0x39, 0x41, 0x48, 0x14, 0x81, 0x00,
  0x00
};

// Set false to test raw detection only (e.g. with a plain NFC card).
const bool TRY_SELECT = true;

// Per-poll timeout. Long enough for a phone's NFC controller to answer,
// short enough that the hit rate below reflects "how quickly does it lock
// on" rather than hiding misses behind one very long wait.
const uint16_t POLL_TIMEOUT_MS = 200;

// Gap after a hit so one held phone isn't counted 50 times in a second.
const uint16_t HIT_COOLDOWN_MS = 1500;

unsigned long attempts = 0;
unsigned long hits = 0;
unsigned long selectAnswered = 0;
unsigned long lastReport = 0;

void printHex(const uint8_t* buf, uint8_t len) {
  for (uint8_t i = 0; i < len; i++) {
    if (buf[i] < 0x10) Serial.print('0');
    Serial.print(buf[i], HEX);
    Serial.print(' ');
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("[BOOT] PN532 detection test");

  Wire.begin(SDA_PIN, SCL_PIN);
  // 100kHz is the safe default; if hit rate is bad, this is one of the knobs
  // worth trying (lower = more tolerant of PN532 clock stretching).
  Wire.setClock(100000);
  nfc.begin();

  uint32_t v = nfc.getFirmwareVersion();
  if (!v) {
    Serial.println("[FATAL] PN532 not found -- check wiring / I2C mode switch.");
    while (1) delay(1000);
  }
  Serial.print("[BOOT] PN532 firmware v");
  Serial.print((v >> 16) & 0xFF);
  Serial.print('.');
  Serial.println((v >> 8) & 0xFF);

  nfc.SAMConfig();
  Serial.println("[BOOT] Ready. Hold a card or phone to the antenna.");
}

void loop() {
  uint8_t uid[7];
  uint8_t uidLen = 0;

  attempts++;
  bool found = nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLen, POLL_TIMEOUT_MS);

  if (found) {
    hits++;
    Serial.print("[HIT] UID (");
    Serial.print(uidLen);
    Serial.print(" bytes): ");
    printHex(uid, uidLen);
    // Android HCE phones present a random 4-byte UID starting 08; a real
    // card has a fixed UID. Handy for telling which one you just detected.
    Serial.println(uidLen == 4 && uid[0] == 0x08 ? " <- looks like a phone (random UID)" : "");

    if (TRY_SELECT) {
      uint8_t resp[64];
      uint8_t respLen = sizeof(resp);
      unsigned long t0 = millis();
      bool ok = nfc.inDataExchange((uint8_t*)SELECT_APDU, sizeof(SELECT_APDU), resp, &respLen);
      unsigned long dt = millis() - t0;

      if (ok && respLen >= 2) {
        selectAnswered++;
        Serial.print("[SELECT] answered in ");
        Serial.print(dt);
        Serial.print("ms, ");
        Serial.print(respLen);
        Serial.print(" bytes: ");
        printHex(resp, respLen);
        Serial.println();
      } else {
        Serial.print("[SELECT] no valid answer (ok=");
        Serial.print(ok);
        Serial.print(", len=");
        Serial.print(respLen);
        Serial.println(")");
      }
    }
    delay(HIT_COOLDOWN_MS);
  }

  // Rolling summary every 5s so the rate is visible without counting lines.
  if (millis() - lastReport > 5000) {
    lastReport = millis();
    Serial.print("[STATS] polls=");
    Serial.print(attempts);
    Serial.print(" hits=");
    Serial.print(hits);
    Serial.print(" select_ok=");
    Serial.println(selectAnswered);
  }
}
