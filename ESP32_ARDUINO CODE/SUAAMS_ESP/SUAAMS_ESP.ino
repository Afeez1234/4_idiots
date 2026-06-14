#include <WiFi.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <MFRC522.h>

#define RST_PIN 22
#define SS_PIN 5

MFRC522 rfid(SS_PIN, RST_PIN); // Create MFRC522 instance.

//Wifi credentials
const char* ssid = "Airtel_4G_SMARTBOX_A9DE";
const char* password = "6A1A68D5";

const char* serverName = "http://192.168.1.198:5000/attendance"; 

void setup() {
  // put your setup code here, to run once:
  Serial.begin(9600);
  delay(1000); // Wait for serial money to initialize
  Serial.println("Initializing RFID reader...");
  SPI.begin(); 
  rfid.PCD_Init(); // Initialize MFRC522

  // Connect to Wi-Fi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.println("Connecting to WiFi...");
  }
  Serial.println("Connected to WiFi");
  Serial.println(WiFi.localIP());
}

void loop() {
  // put your main code here, to run repeatedly:
  // Check if a card is present
  if (!rfid.PICC_IsNewCardPresent()) {
    return;
  }
  
  // Read the card
  if (!rfid.PICC_ReadCardSerial()) {
    return;
  }
  
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    uid += String(rfid.uid.uidByte[i], HEX);
  }

  uid.toUpperCase();

  Serial.println("Card UID: " + uid);

  // Send UID to server
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
  delay(500); // Delay to avoid multiple reads of the same card
}
