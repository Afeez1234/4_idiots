// OLED bench test: finds the screen and draws on it.
//
// Run this when the terminal's OLED stays dark. It scans BOTH I2C buses
// the terminal uses and says what it finds:
//   - bus 1, GPIO 25/26: where the terminal expects the OLED (oled_display.ino)
//   - bus 0, GPIO 21/22: the PN532's bus, in case the OLED was wired there
// then, if a screen answers, fills it white for a second and writes text.
//
// Same libraries as the terminal: Adafruit SSD1306 + Adafruit GFX.
// Serial monitor at 115200.

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

TwoWire bus1 = TwoWire(1);

// Prints every address that answers; returns the first OLED-looking one
// (0x3C or 0x3D), or 0 if none.
uint8_t scan(TwoWire& bus, const char* name) {
  Serial.printf("Scanning %s...\n", name);
  uint8_t oledAddr = 0;
  uint8_t found = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    bus.beginTransmission(addr);
    if (bus.endTransmission() == 0) {
      found++;
      const char* what = (addr == 0x3C || addr == 0x3D) ? "  <- OLED"
                       : (addr == 0x24) ? "  <- PN532" : "";
      Serial.printf("  found device at 0x%02X%s\n", addr, what);
      if (!oledAddr && (addr == 0x3C || addr == 0x3D)) oledAddr = addr;
    }
  }
  if (!found) Serial.println("  nothing answered");
  return oledAddr;
}

void tryScreen(TwoWire& bus, uint8_t addr, const char* name) {
  Adafruit_SSD1306 oled(128, 64, &bus, -1);
  if (!oled.begin(SSD1306_SWITCHCAPVCC, addr)) {
    Serial.printf("Screen at 0x%02X on %s answered but wouldn't start (out of memory?)\n", addr, name);
    return;
  }
  Serial.printf("Drawing on the screen at 0x%02X on %s -- it should go white, then show text\n", addr, name);
  oled.fillScreen(SSD1306_WHITE);
  oled.display();
  delay(1000);
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(2);
  oled.setCursor(0, 0);
  oled.print("OLED OK");
  oled.setTextSize(1);
  oled.setCursor(0, 24);
  oled.print(name);
  oled.setCursor(0, 40);
  oled.printf("address 0x%02X", addr);
  oled.display();
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println("\n=== OLED test ===");

  bus1.begin(25, 26, 400000);
  uint8_t a1 = scan(bus1, "bus 1 (SDA 25, SCL 26) -- where the terminal expects the OLED");

  Wire.begin(21, 22, 100000);
  uint8_t a0 = scan(Wire, "bus 0 (SDA 21, SCL 22) -- the PN532's bus");

  if (a1) {
    tryScreen(bus1, a1, "SDA25 SCL26");
  } else if (a0) {
    Serial.println("The OLED is on the PN532's pins (21/22). Move its SDA to GPIO 25 and SCL to GPIO 26.");
    tryScreen(Wire, a0, "SDA21 SCL22");
  } else {
    Serial.println();
    Serial.println("No OLED found on either bus. Check, in this order:");
    Serial.println("  1. VCC to 3V3 and GND to GND (a dark screen with no power looks the same as a broken one)");
    Serial.println("  2. SDA and SCL not swapped: OLED SDA -> GPIO 25, OLED SCL -> GPIO 26");
    Serial.println("  3. Pin labels: on some boards the order is VCC GND SCL SDA, on others GND VCC SCL SDA");
    Serial.println("  4. Loose jumper wires -- press them in, or try new ones");
  }
  Serial.println("=== done ===");
}

void loop() {}
