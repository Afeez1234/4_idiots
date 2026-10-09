# SUAAMS Hardware Notes

Everything about the terminal that I would otherwise rediscover the hard way.
Sources: the firmware source, git history, and the Arduino IDE settings and
libraries installed on the dev PC (read 2026-10-09). Lines marked
**FILL IN** can only come from looking at, or measuring, the physical
hardware. Fill them in while it's on the desk.

---

## 1. Parts

| Part | Role | Notes |
|---|---|---|
| ESP32 board | Runs the terminal: Wi-Fi, BLE, NFC loop | Built as **ESP32 Dev Module** (classic ESP32, 4 MB flash, no PSRAM). **FILL IN:** the name printed on the physical board, if it's a specific DevKit. The firmware logs free heap because Wi-Fi + HTTPS + BLE together is tight on a classic ESP32 |
| PN532 NFC module | Reads the phone's HCE response | I²C mode. Replaced the MFRC522 because it can hold an ISO 14443-4 APDU exchange with a phone |
| Power supply | | **FILL IN:** source, voltage, current |
| Enclosure / mounting | | **FILL IN** |

The old prototype (MFRC522 reading RFID cards) lives in `SUAAMS_ESP/` and
`SUAAMS_/`, for reference only.

## 2. Wiring

| Signal | PN532 pin | ESP32 pin |
|---|---|---|
| SDA | SDA | **GPIO 21** |
| SCL | SCL | **GPIO 22** |
| VCC | VCC | **FILL IN:** 3V3 or 5V/VIN pin? The module accepts either; the bench sketch suggests 5 V if detection is poor |
| GND | GND | GND |
| IRQ / RESET | not connected | Not used (`PN532_IRQ = -1`, `PN532_RESET = -1`) |

The I²C clock is set to **100 kHz** (`Wire.setClock(100000)`). The Wire
default is usually 400 kHz. The PN532 is the slower device, and the faster
clock can drop bytes.

## 3. PN532 mode switches

The PN532 module has DIP switches (or jumpers) that select its interface. I²C
only works with the right positions.

- **I²C = switch 1 ON, switch 2 OFF.** This is the standard setting on the
  common red "PN532 NFC RFID V3" board. For reference, HSU (UART) is both
  OFF and SPI is 1 OFF, 2 ON. **FILL IN:** confirm against the table printed
  on your board, then delete this note. Power-cycle after changing the
  switches, because the chip only reads them at power-on.
- **Symptom when wrong:** the serial monitor prints
  `[FATAL] PN532 not found -- check wiring/interface selection.` and the board
  stops there. It halts on purpose, and no Wi-Fi or BLE starts.
- **Bench-test sketch:** `ESP32_ARDUINO CODE/PN532_DetectTest/`. Run it first
  whenever a reader seems dead. It reads the same pins and clock as the
  terminal, and prints a rolling `[STATS]` hit rate every 5 s.

## 4. Firmware setup

- **Sketch:** `ESP32_ARDUINO CODE/SUAAMS_HCE/SUAAMS_HCE.ino`
- **Secrets:** copy `secrets.h.example` to `secrets.h`. It holds Wi-Fi, the
  three URLs (check-in, healthz, backlog), `TERMINAL_ID` + `TERMINAL_SECRET`,
  `BLE_BEACON_SECRET` and `BLE_TERMINAL_NUMBER`. The secrets must match the
  server's `.env`. Set `BLE_BEACON_SECRET` to `""` to turn Bluetooth off. An
  old `secrets.h` without the BLE lines fails the build with a clear error.
- **Libraries** (installed versions):
  - Adafruit PN532 **1.3.4**. In this version `inListPassiveTarget()` takes
    no arguments.
  - Adafruit BusIO, a dependency of Adafruit PN532.
  - NimBLE-Arduino **2.5.1**.
  - mbedTLS (HMAC) comes with the ESP32 core.
  - The `MFRC522` library is also installed, but only the old prototype uses it.
- **Board package:** esp32 by Espressif **3.3.12** (from the Boards Manager
  URL `https://espressif.github.io/arduino-esp32/package_esp32_index.json`).
  Any 3.x works. The sketch refuses to compile on 2.x because it needs the
  core's built-in CA bundle for certificate checks.
- **Tools menu settings** that build a working terminal:

  | Setting | Value |
  |---|---|
  | Board | ESP32 Dev Module |
  | Partition Scheme | **Huge APP (3MB No OTA)**. Required: BLE + Wi-Fi + HTTPS don't fit the default 1.2 MB app partition. It also means **no over-the-air updates**, so flashing needs USB |
  | Flash Size | 4MB |
  | Flash Mode / Freq | QIO / 80 MHz |
  | CPU Frequency | 240 MHz |
  | PSRAM | Disabled |
  | Arduino / Events core | Core 1 / Core 1 |
  | Upload Speed | 921600. Drop to 115200 if uploads fail |
  | Core Debug Level | None |
  | Erase All Flash | Disabled. Enabling it wipes the offline queue in NVS |
- **Serial monitor:** 115200 baud.

## 5. Protocol constants

| Thing | Value | Must match |
|---|---|---|
| NFC AID | `F0394148148100` | `apduservice.xml`, `SuaamsHceService.kt`, both sketches |
| SELECT APDU | `00 A4 04 00 07 F0 39 41 48 14 81 00 00` | — |
| Success status | `90 00` after the 32-char code | `SuaamsHceService.kt` |
| "No code armed" status | `6A 88`, not an error | `SuaamsHceService.kt` |
| BLE company ID | `0xFFFF` (SIG "testing" ID) | `ble_scan_service.dart` |
| BLE payload | 14 bytes: terminal(2) ‖ slot(4) ‖ code(8) | `ble_beacon.py` |
| BLE slot | 5 s | `ble_beacon.py` `SLOT_SECONDS` |
| BLE advert interval | 100 ms (160 × 0.625 ms), non-connectable | — |

## 6. Behaviour to remember

| Behaviour | Value | Why |
|---|---|---|
| NFC code size | 34 bytes, single APDU exchange (about 0.1 s) | The old ~360-byte JWT in six chunks kept failing |
| Code lifetime | 10 s from mint | 3 s rejected real students who were still positioning the phone |
| Read cooldown | 2 s between reads | Stops one held phone being read repeatedly. It is not the duplicate defence; the server is |
| POST retries | 2 attempts, only on transport failure (`-1`), 1.5 s apart | Safe because the submit is idempotent. A real 4xx/5xx is never retried |
| HTTP timeout | 6 s | 15 s used to hold the field for 16–20 s just to be told "expired" |
| BLE broadcast | New code every 5 s; server accepts current ±1 slot | Limits how long a relayed code is useful |
| BLE before NTP | Broadcasts nothing | A code from a 1970 clock would only be rejected |
| BLE self-test | Known-answer check at boot; refuses to broadcast on mismatch | Proves firmware and server compute the same HMAC |
| Offline queue | Up to 16 taps in NVS flash (survives power loss), oldest dropped when full, flushed every 30 s when the field is empty | Stored as "pending verification". Expired codes must not become automatic attendance |
| Keep-alive ping | At boot, every 4 minutes when idle, and before a POST if not confirmed warm in 60 s | Render free tier sleeps and took 8.5 s to wake, longer than a code lasts |
| TLS | Server certificate verified against the core's CA bundle (chain + hostname, not expiry) | Stops a fake server on the venue Wi-Fi collecting the terminal secret. Was `setInsecure()` |
| Wi-Fi at boot | Waits 20 s at most, then carries on offline and retries every 5 s | Used to loop forever and wedge the board until a power cycle |
| Wi-Fi + BLE | Share one radio (coexistence is handled by the ESP32 core) | **FILL IN:** whether BLE has ever dropped out during uploads. Also note the lowest `[HEAP] lowest-ever` value seen after a run of taps |

## 7. Troubleshooting log

Add a row every time something goes wrong. Future me will thank me.

| Symptom | Cause | Fix | Fixed in git |
|---|---|---|---|
| `[FATAL] PN532 not found` at boot | DIP switches not set for I²C, or wiring | Set I²C mode (section 3), check SDA/SCL, run `PN532_DetectTest` | |
| Bench sketch says the phone is "never detected" | `readPassiveTargetID(MIFARE)` can't see an HCE phone, which is an ISO 14443-4 target | Use `inListPassiveTarget()`; a bench run showed `list` hits while `card` was always `n` | 2026-08-01 (terminal); bench sketch 2026-09-26 |
| `SELECT ok=0` / "Don't know how to handle this command: 81" | The legacy MIFARE probe in the previous cycle left the PN532 in a bad state | Keep `COMPARE_WITH_LEGACY_PROBE = false` | 2026-09-26 |
| Intermittent reads | *Suspected:* I²C running at the 400 kHz default (not proven to be the cause) | `Wire.setClock(100000)` | 2026-09-26 |
| Phone detected but SELECT silent | HCE service not engaging | Check the AID matches exactly, the app is installed and open, and the screen is on and unlocked | |
| Terminal gets `6A 88` | Phone has no code armed: not in a check-in, window over, or tapped before the code was handed to native | Normal. If it happens every time, check the app sets the token *before* showing "tap now" (fixed in `nfc_provider.dart`) | |
| 401 on check-in POST, especially after idle | Code expired before the server saw it, usually a cold-start server | Keep-alive ping (section 6); check the `[WARM]` log lines | |
| POSTs taking 16–20 s, then nothing | 15 s HTTP timeout against a cold or unreachable server | Timeout cut to 6 s; failures go to the offline queue | 2026-09-28 |
| First tap after power-on always failed | First warm ping waited a full 4 min | Ping forced at the end of `setup()` | 2026-09-28 |
| Warm ping never fired while a phone was resting on the reader | Ping only ran when the field was empty | Pre-flight ping in `ensureBackendWarmForPost()` | 2026-09-28 |
| Board stuck at boot with no Wi-Fi | Unbounded `while (!connected)` loop | Bounded wait, then degraded mode | 2026-09-26 |
| Every request `-1`, log shows `[WARM]`/`[POST]`/`[QUEUE] TLS error ...` | Server certificate doesn't chain to a root in the core's CA bundle, or the URL hostname doesn't match it | Check the URLs in `secrets.h` are the real hostname; update the board package if the CA bundle is old. Taps go to the offline queue meanwhile | 2026-10-09 (verification added) |
| BLE codes always rejected | Terminal and server `BLE_BEACON_SECRET` differ, or clocks disagree | Copy a `[BLE] Broadcasting` hex line into `python ble_beacon.py <hex>` on the server side. It tells you which one | |
| | | | |

## 8. Measurements (for the report / defence)

Measured so far, as recorded in code comments:

- Bench SELECT round-trip: **104 ms** (`PN532_DetectTest`, first bench run).
  This is the figure to quote for "how long does the NFC read take". An
  earlier ~30 ms figure was a design estimate, not a measurement.
- Bench detection rate: 34% of poll cycles with the phone held (8 of 23).
  That run also had the legacy probe on, which disrupts the next cycle, so
  treat it as a lower bound and re-measure with the probe off.
- 6-chunk JWT era, for comparison: ~650 ms of RF time; link degraded after
  ~119 bytes
- Warm end-to-end budget: about 0.5 s (APDU ~0.12 s, TLS + POST ~0.3 s,
  DB write ~0.1 s)
- Cold Render start: 8.5 s. Barely warm: 5.0–5.3 s
Still to measure. **FILL IN**, with the date and the phone model:

- Tap to app confirmation, server warm: **?** (read `[POST] Completed in`
  on the serial monitor and the time until the app shows success)
- Reliable read distance: **?** (count 10 taps at each of 0, 1, 2 and 3 cm)
- Detection rate with the legacy probe off: **?** (`PN532_DetectTest`
  `[STATS]` line)
- BLE range through a lecture hall: **?** (the app treats RSSI ≥ −75 dBm as
  "strong", and the server logs every RSSI it receives)
- Wi-Fi dropped mid-class: **?** (pull the router; expect `[QUEUE] Queued`
  lines, then `[QUEUE] Flushing` once it's back)
