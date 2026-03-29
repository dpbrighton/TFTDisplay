#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <TFT_eSPI.h>
#include "config.h"

TFT_eSPI tft = TFT_eSPI();

// ============================================================
// Setup
// ============================================================
void setup() {
    Serial.begin(115200);

    // Initialise display
    tft.init();
    tft.setRotation(0);       // Portrait — adjust if needed
    tft.fillScreen(TFT_BLACK);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.setTextSize(2);
    tft.setCursor(10, 10);
    tft.println("Connecting...");

    // Connect to WiFi
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.print("Connecting to WiFi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();
    Serial.print("Connected: ");
    Serial.println(WiFi.localIP());

    tft.fillScreen(TFT_BLACK);
    tft.setCursor(10, 10);
    tft.println("WiFi OK");
    tft.println(WiFi.localIP().toString());
    delay(1500);

    tft.fillScreen(TFT_BLACK);
    tft.setCursor(10, 10);
    tft.println("TFT Display");
    tft.println("Ready.");
}

// ============================================================
// Main loop
// ============================================================
void loop() {
    // Phase 1 dashboard and further phases will be built here
    delay(1000);
}
