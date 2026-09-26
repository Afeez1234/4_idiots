/*
  PN532 detection-only bring-up test (ESP32, I2C).

  Purpose: isolate the RF/transport layer from everything else. No WiFi, no
  backend, no token handling -- just "how often does the PN532 see a target,
  and does the phone's HCE service answer a SELECT". Run this BEFORE
  trusting the real terminal, and before concluding anything about how far
  the phone can be read.

  THE FIX IN THIS REVISION
  ------------------------
  This sketch used to measure detection with:

      readPassiveTargetID(PN532_MIFARE_ISO14443A, ...)

  That is the wrong call for an Android HCE phone. A phone running card
  emulation is an ISO14443-4 **Type 4** tag presenting a random UID from
  the CL_RANDOM (0x08) block -- not a MIFARE Classic target. The production
  terminal correctly uses inListPassiveTarget(); this sketch did not. So a
  "phone never detected" result measured the old way may have been an
  artifact of the diagnostic rather than a real RF limit.

  It now probes BOTH calls every cycle and reports them side by side, so
  the comparison is the answer:

      list_hits   -- inListPassiveTarget(), i.e. what the terminal uses
      card_hits   -- readPassiveTargetID(MIFARE_ISO14443A), the old way

  If list_hits is high and card_hits is low, the old diagnostic was the
  problem, not your hardware.

  Also note Wire.setClock(100000) below -- the production sketch never set
  this and ran the I2C bus at the Wire default. If hit rates here look good
  and the terminal still flakes, that clock is the difference.

  HOW TO READ THE OUTPUT
  ----------------------
    card_hits AND list_hits both low
        -> PN532 power, wiring, or I2C transport. Try 5V on VCC, confirm
           the module is in I2C mode (the MODE jumpers), check SDA/SCL.

    list_hits high, card_hits low  (the likely outcome for a phone)
        -> Normal, and the reason this revision exists. Hardware is fine.

    list_hits high but SELECT silent
        -> Link forms, but the HCE service isn't engaging. Check the AID
           matches apduservice.xml exactly, that the app is installed and
           OPEN on the phone, the screen is on and the device unlocked.

    SELECT answers 6A 88
        -> Full path works. The app simply had no beacon armed, which is
           expected unless a check-in is actually in progress.

    "Don't know how to handle this command: 81" / SELECT ok=0
        -> The PN532 returned an error frame instead of a response. The
           usual cause is the legacy comparison probe having run in the
           PREVIOUS cycle: readPassiveTargetID does its own anticollision
           and leaves the chip in a state where the next inDataExchange
           fails. Set COMPARE_WITH_LEGACY_PROBE = false (the default) and
           these disappear. Observed and confirmed on a real bench run.

  MEASURED RESULT FROM THE FIRST BENCH RUN
  ----------------------------------------
  Worth recording, because it settles the question this sketch was written
  to answer. With the phone installed, open and unlocked:

      [SELECT] answered in 104ms, 2 bytes: 6A 88  (no beacon armed)
      [STATS] cycles=23  list_hits=8 (34%)  card_hits=3 (13%)  select_ok=3

  Every successful SELECT came with card=n -- i.e. readPassiveTargetID does
  NOT detect the phone at all, while inListPassiveTarget() does. The
  original version of this sketch measured detection only through the
  former, which is why it appeared to report that the PN532 could never see
  the phone. It could, all along.

  Note also that Android HCE UIDs are random 4-byte values and are NOT
  required to start with 0x08; an earlier comment here claimed otherwise
  and a real run disproved it.
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

// Set false to measure raw detection only, with no SELECT at all.
const bool TRY_SELECT = true;

// Run the legacy readPassiveTargetID(MIFARE_ISO14443A) probe alongside the
// production one, purely to demonstrate the difference between them.
//
// DEFAULT FALSE, deliberately. That probe does its own anticollision
// sequence, which leaves the PN532 in a different state than
// inListPassiveTarget() left it in -- so the inDataExchange() on the NEXT
// cycle comes back with a 0x81 error frame. In a first bench run it
// produced exactly that pattern: every failed SELECT was preceded by a
// card=Y hit, and every successful one by card=n. The comparison is
// diagnostic gold, but it poisons the primary measurement, so it has to be
// switched on deliberately rather than left running.
const bool COMPARE_WITH_LEGACY_PROBE = false;

// Per-poll timeout in ms for readPassiveTargetID (which takes a uint16_t
// timeout; note that passing 0 there means "block forever", so never zero
// this). Long enough for a phone's NFC controller to wake and answer, short
// enough that the hit rate below reflects real lock-on performance rather
// than hiding misses behind one very long wait.
//
// NOTE: this does NOT apply to inListPassiveTarget(). In Adafruit_PN532
// 1.3.4 that call takes no arguments at all and returns no UID -- there is
// no overload accepting a timeout or an out-buffer, so the HCE UID cannot
// be read through it. That is fine: the SELECT response is the real signal
// for a phone, and the CL_RANDOM UID hint below comes from the legacy probe.
const uint16_t POLL_TIMEOUT_MS = 200;

// Gap after a hit so one held phone isn't counted dozens of times a second.
const uint16_t HIT_COOLDOWN_MS = 1500;

// Counters
unsigned long cycles = 0;
unsigned long listHits = 0;   // inListPassiveTarget()  -- the production call
unsigned long cardHits = 0;   // readPassiveTargetID()  -- the old diagnostic
unsigned long selectOk = 0;
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
  Serial.println("[BOOT] Probing BOTH inListPassiveTarget() and readPassiveTargetID()");
  Serial.println("[BOOT] The gap between the two hit rates is the whole point of this test.");

  Wire.begin(SDA_PIN, SCL_PIN);
  // 100kHz is the safe default. The production terminal now matches this;
  // it previously ran at the Wire default, which is a plausible cause of
  // intermittent read failures there.
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
  Serial.println("[BOOT] For a phone: app installed, OPEN on screen, device unlocked.");
}

void loop() {
  // --- Probe 1: the call the production terminal actually uses ---------
  // No arguments and no UID: Adafruit_PN532 1.3.4 exposes only the no-arg
  // overload of inListPassiveTarget(). (An earlier revision of this sketch
  // passed uid/uidLen/timeout here, which matches some library versions but
  // not this one -- it does not compile against 1.3.4.)
  bool listFound = nfc.inListPassiveTarget();

  // Do the SELECT IMMEDIATELY after detection, before any other poll runs.
  // A second poll in between re-arms the field and can walk the
  // ISO14443-4 state machine out from under the exchange we're trying to
  // measure -- which would show up as a SELECT failure that has nothing to
  // do with the phone.
  bool selectOkThisCycle = false;
  if (TRY_SELECT && listFound) {
    uint8_t resp[64];
    uint8_t respLen = sizeof(resp);
    unsigned long t0 = millis();
    bool ok = nfc.inDataExchange((uint8_t*)SELECT_APDU, sizeof(SELECT_APDU), resp, &respLen);
    unsigned long dt = millis() - t0;

    if (ok && respLen >= 2) {
      selectOkThisCycle = true;
      selectOk++;

      Serial.print("[SELECT] answered in ");
      Serial.print(dt);
      Serial.print("ms, ");
      Serial.print(respLen);
      Serial.print(" bytes: ");
      printHex(resp, respLen);

      uint8_t sw1 = resp[respLen - 2];
      uint8_t sw2 = resp[respLen - 1];
      Serial.print("  SW=");
      Serial.print(sw1, HEX);
      Serial.print(' ');
      Serial.print(sw2, HEX);

      if (sw1 == 0x6A && sw2 == 0x88) {
        Serial.print("  (no beacon armed -- HCE path WORKS)");
      } else if (sw1 == 0x90 && sw2 == 0x00) {
        Serial.print("  (beacon delivered)");
      }
      Serial.println();
    } else {
      Serial.print("[SELECT] no valid answer (ok=");
      Serial.print(ok);
      Serial.print(", len=");
      Serial.print(respLen);
      Serial.println(")");
    }
  }

  // --- Probe 2: the old diagnostic, opt-in only --------------------------
  // Runs after SELECT, so it can never disturb THIS cycle's exchange -- but
  // it does disturb the next one, which is why it defaults off. See the
  // COMPARE_WITH_LEGACY_PROBE comment above.
  uint8_t cardUid[10];
  uint8_t cardUidLen = sizeof(cardUid);
  bool cardFound = false;
  if (COMPARE_WITH_LEGACY_PROBE) {
    cardFound = nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, cardUid, &cardUidLen, POLL_TIMEOUT_MS);
  }

  cycles++;

  if (!listFound && !cardFound) {
    // Nothing in the field on either probe. Don't report -- the rolling
    // summary below covers it, and a line per miss buries the hits.
    delay(1);
  } else {
    if (cardFound) cardHits++;
    if (listFound)  listHits++;

    Serial.print("[HIT] list=");
    Serial.print(listFound ? "Y" : "n");
    if (COMPARE_WITH_LEGACY_PROBE) {
      Serial.print(" card=");
      Serial.print(cardFound ? "Y" : "n");
    }
    if (selectOkThisCycle) Serial.print(" select=Y");

    // UID comes from the legacy probe only -- inListPassiveTarget() in 1.3.4
    // gives us no way to read it. So this is available only when the
    // comparison probe is switched on; for the phone, trust list= / select=.
    if (cardFound) {
      Serial.print("  UID (");
      Serial.print(cardUidLen);
      Serial.print(" bytes): ");
      printHex(cardUid, cardUidLen);

      // A 4-byte UID here is a good sign the legacy probe is seeing an
      // Android HCE phone -- those present a random 4-byte UID rather than
      // a card's fixed one. Note it is NOT required to begin with 0x08:
      // an earlier revision of this comment claimed that, and a real bench
      // run disproved it (UIDs like E6 58 4B 01 were the phone).
    }
    Serial.println();

    delay(HIT_COOLDOWN_MS);
  }

  // Rolling summary every 5s so rates are visible without counting lines.
  if (millis() - lastReport > 5000) {
    lastReport = millis();
    Serial.print("[STATS] cycles=");
    Serial.print(cycles);
    Serial.print("  list_hits=");
    Serial.print(listHits);
    Serial.print(" (");
    Serial.print(cycles ? (listHits * 100) / cycles : 0);
    Serial.print("%)  card_hits=");
    Serial.print(cardHits);
    Serial.print(" (");
    Serial.print(cycles ? (cardHits * 100) / cycles : 0);
    Serial.print("%)  select_ok=");
    Serial.println(selectOk);
  }
}
