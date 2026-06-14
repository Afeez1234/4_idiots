#include <SPI.h>
#include <MFRC522.h>

#define SS_PIN 10
#define RST_PIN 9

MFRC522 mfrc522(SS_PIN, RST_PIN);

void setup() {
  Serial.begin(9600);
  SPI.begin();
  mfrc522.PCD_Init();

  Serial.println("Scan an RFID card...");
}

void loop() {

    // Check if a card is present
    if (!mfrc522.PICC_IsNewCardPresent()) {
      return;
    }
  
    // Read the card
    if (!mfrc522.PICC_ReadCardSerial()) {
      return;
    }
  
//    Serial.print("UID: ");
    String uid = "";
    
    for (byte i = 0; i < mfrc522.uid.size; i++) {
      if (mfrc522.uid.uidByte[i] < 0x10)
        uid += "0";
    
      uid += String(mfrc522.uid.uidByte[i], HEX);
    }
    
    uid.toUpperCase();
    
    Serial.println(uid);
  
    mfrc522.PICC_HaltA();
}
