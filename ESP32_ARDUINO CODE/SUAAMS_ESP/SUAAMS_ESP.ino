#include <WiFi.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <MFRC522.h>

#define RST_PIN 22
#define SS_PIN 5

MFRC522 rfid(SS_PIN, RST_PIN);

const char* ssid = "3RR0R";
const char* password = "samsun225";
//const char* serverName = "http://192.168.1.198:5000/attendance";
const char* serverName = "https://suaams.onrender.com/attendance";

const int DEBOUNCE_DELAY = 3000; // Milliseconds before same card can scan again

String lastUID = "";
unsigned long lastScanTime = 0;

void setup() {
  Serial.begin(9600);
  delay(1000);
  Serial.println("Initializing RFID reader...");

  SPI.begin();
  rfid.PCD_Init();

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.println("Connecting to WiFi...");
  }
  Serial.println("Connected to WiFi");
  Serial.println(WiFi.localIP());
}

void loop() {
  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial()) return;

  // Build UID string with consistent padding
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();

  // Halt card and stop encryption before doing anything else
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();

  // Debounce — ignore same card within DEBOUNCE_DELAY
  if (uid == lastUID && millis() - lastScanTime < DEBOUNCE_DELAY) {
    Serial.println("Duplicate scan ignored: " + uid);
    return;
  }
  lastUID = uid;
  lastScanTime = millis();

  Serial.println("Card UID: " + uid);

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(serverName);
    http.addHeader("Content-Type", "application/json");

    String jsonPayload = "{\"RFID_UID\":\"" + uid + "\"}";

    int httpResponseCode = http.POST(jsonPayload);
    String response = http.getString();

    Serial.println("HTTP Response code: " + String(httpResponseCode));
    Serial.println("Response: " + response);

    http.end();
  } else {
    Serial.println("WiFi not connected");
  }
}
