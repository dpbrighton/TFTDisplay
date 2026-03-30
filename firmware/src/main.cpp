#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <TFT_eSPI.h>
#include <Preferences.h>
#include "config.h"

// ── Hardware ────────────────────────────────────────────────
TFT_eSPI    tft   = TFT_eSPI();
Preferences prefs;

// ── Screen dimensions (landscape) ──────────────────────────
#define SCREEN_W  320
#define SCREEN_H  240

// ── Layout ─────────────────────────────────────────────────
#define HDR_H   32          // header bar height
#define HTG_H   65          // heating strip height at bottom
#define MID_H   (SCREEN_H - HDR_H - HTG_H)   // 143px — light buttons area
#define DIV_X   (SCREEN_W / 2)                // vertical divider at x=160

// Button size inside each light section
#define BTN_W   70
#define BTN_H   44

// ── Colors (RGB565) ─────────────────────────────────────────
#define C_BG       0x10A2   // near-black
#define C_HEADER   0x0233   // dark navy
#define C_ON       0x0400   // dark green (button not active)
#define C_ON_ACT   0x07E0   // bright green (light is ON)
#define C_OFF_ACT  0xC000   // dark red (light is OFF and btn highlighted)
#define C_OFF      0x2945   // dark grey (inactive)
#define C_DIVIDER  0x4208   // mid grey
#define C_WARM     0xFCA0   // orange for active heating
#define C_TEXT     0xFFFF   // white
#define C_SUBTEXT  0xC618   // light grey

// ── State ───────────────────────────────────────────────────
struct {
    bool  drOn    = false;
    bool  lampsOn = false;
    float curTemp = 0.0f;
    float tgtTemp = 20.0f;
    bool  hvacOn  = false;
    bool  wifiOk  = false;
} dash;

unsigned long lastPoll = 0;

// ── HA REST helpers ─────────────────────────────────────────
String haGet(const char* entity) {
    if (WiFi.status() != WL_CONNECTED) return "";
    HTTPClient http;
    char url[128];
    snprintf(url, sizeof(url), "http://%s:%d/api/states/%s", HA_HOST, HA_PORT, entity);
    http.begin(url);
    http.addHeader("Authorization", "Bearer " HA_TOKEN);
    http.addHeader("Content-Type", "application/json");
    String payload = "";
    if (http.GET() == 200) payload = http.getString();
    http.end();
    return payload;
}

bool haPost(const char* domain, const char* service, const String& body) {
    if (WiFi.status() != WL_CONNECTED) return false;
    HTTPClient http;
    char url[128];
    snprintf(url, sizeof(url), "http://%s:%d/api/services/%s/%s", HA_HOST, HA_PORT, domain, service);
    http.begin(url);
    http.addHeader("Authorization", "Bearer " HA_TOKEN);
    http.addHeader("Content-Type", "application/json");
    int code = http.POST(body);
    http.end();
    return (code == 200 || code == 201);
}

bool entityIsOn(const char* entity) {
    String r = haGet(entity);
    if (r.isEmpty()) return false;
    JsonDocument doc;
    deserializeJson(doc, r);
    return strcmp(doc["state"] | "", "on") == 0;
}

// ── Poll HA state ───────────────────────────────────────────
void pollHA() {
    dash.drOn = entityIsOn(ENTITY_DR_LIGHT_1) ||
                entityIsOn(ENTITY_DR_LIGHT_2) ||
                entityIsOn(ENTITY_DR_LIGHT_3) ||
                entityIsOn(ENTITY_DR_LIGHT_4);

    dash.lampsOn = entityIsOn(ENTITY_OLD_LAMP) ||
                   entityIsOn(ENTITY_LAMP_SOCKET);

    String r = haGet(ENTITY_TRV);
    if (!r.isEmpty()) {
        JsonDocument doc;
        deserializeJson(doc, r);
        dash.curTemp = doc["attributes"]["current_temperature"] | 0.0f;
        dash.tgtTemp = doc["attributes"]["temperature"]         | 20.0f;
        const char* action = doc["attributes"]["hvac_action"]   | "idle";
        dash.hvacOn = strcmp(action, "heating") == 0;
    }
}

// ── HA actions ──────────────────────────────────────────────
void setDrawingRoomLights(bool on) {
    const char* svc = on ? "turn_on" : "turn_off";
    haPost("light", svc, "{\"entity_id\":\"" ENTITY_DR_LIGHT_1 "\"}");
    haPost("light", svc, "{\"entity_id\":\"" ENTITY_DR_LIGHT_2 "\"}");
    haPost("light", svc, "{\"entity_id\":\"" ENTITY_DR_LIGHT_3 "\"}");
    haPost("light", svc, "{\"entity_id\":\"" ENTITY_DR_LIGHT_4 "\"}");
    dash.drOn = on;
}

void setLamps(bool on) {
    const char* svc = on ? "turn_on" : "turn_off";
    haPost("light",  svc, "{\"entity_id\":\"" ENTITY_OLD_LAMP    "\"}");
    haPost("switch", svc, "{\"entity_id\":\"" ENTITY_LAMP_SOCKET "\"}");
    dash.lampsOn = on;
}

void adjustTemp(float delta) {
    float t = constrain(dash.tgtTemp + delta, 5.0f, 30.0f);
    char body[128];
    snprintf(body, sizeof(body),
             "{\"entity_id\":\"" ENTITY_TRV "\",\"temperature\":%.1f}", t);
    haPost("climate", "set_temperature", body);
    dash.tgtTemp = t;
}

// ── Drawing helpers ─────────────────────────────────────────
void drawBtn(int x, int y, int w, int h, const char* label, bool active, uint16_t activeCol) {
    uint16_t bg = active ? activeCol : C_OFF;
    tft.fillRoundRect(x, y, w, h, 6, bg);
    tft.drawRoundRect(x, y, w, h, 6, active ? C_TEXT : C_DIVIDER);
    tft.setTextColor(C_TEXT, bg);
    tft.setTextDatum(MC_DATUM);
    tft.setTextSize(2);
    tft.drawString(label, x + w / 2, y + h / 2);
}

void drawHeader() {
    tft.fillRect(0, 0, SCREEN_W, HDR_H, C_HEADER);
    tft.setTextColor(C_TEXT, C_HEADER);
    tft.setTextDatum(ML_DATUM);
    tft.setTextSize(2);
    tft.drawString("LIVING ROOM", 8, HDR_H / 2);
    // WiFi status dot
    tft.fillCircle(SCREEN_W - 12, HDR_H / 2, 6,
                   dash.wifiOk ? (uint16_t)C_ON_ACT : (uint16_t)C_OFF_ACT);
}

void drawLightSection(int startX, const char* title, bool isOn) {
    int w = DIV_X;
    tft.fillRect(startX, HDR_H, w, MID_H, C_BG);

    // Section title
    tft.setTextColor(C_SUBTEXT, C_BG);
    tft.setTextDatum(TC_DATUM);
    tft.setTextSize(1);
    tft.drawString(title, startX + w / 2, HDR_H + 6);

    // Status dot
    tft.fillCircle(startX + w / 2, HDR_H + 26, 9,
                   isOn ? (uint16_t)C_ON_ACT : (uint16_t)C_DIVIDER);

    // ON / OFF buttons
    int btnY  = HDR_H + MID_H - BTN_H - 10;
    int btnOnX  = startX + w / 2 - BTN_W - 4;
    int btnOffX = startX + w / 2 + 4;
    drawBtn(btnOnX,  btnY, BTN_W, BTN_H, "ON",  isOn,  C_ON_ACT);
    drawBtn(btnOffX, btnY, BTN_W, BTN_H, "OFF", !isOn, C_OFF_ACT);
}

void drawHeatingSection() {
    int y  = SCREEN_H - HTG_H;
    uint16_t bg = dash.hvacOn ? 0x2000 : (uint16_t)C_BG;
    tft.fillRect(0, y, SCREEN_W, HTG_H, bg);
    tft.drawFastHLine(0, y, SCREEN_W, C_DIVIDER);

    // Label
    tft.setTextColor(dash.hvacOn ? (uint16_t)C_WARM : (uint16_t)C_SUBTEXT, bg);
    tft.setTextDatum(ML_DATUM);
    tft.setTextSize(1);
    tft.drawString(dash.hvacOn ? "HEATING" : "HEATING", 10, y + 10);

    // Current temp — large, centred
    char buf[16];
    snprintf(buf, sizeof(buf), "%.1f C", dash.curTemp);
    tft.setTextColor(C_TEXT, bg);
    tft.setTextDatum(MC_DATUM);
    tft.setTextSize(3);
    tft.drawString(buf, SCREEN_W / 2, y + 24);

    // Target temp
    snprintf(buf, sizeof(buf), "Target: %.1f C", dash.tgtTemp);
    tft.setTextSize(1);
    tft.setTextColor(C_SUBTEXT, bg);
    tft.drawString(buf, SCREEN_W / 2, y + 52);

    // - / + buttons flanking the temp
    drawBtn(SCREEN_W / 2 - 80, y + 34, 28, 22, "-", true, C_DIVIDER);
    drawBtn(SCREEN_W / 2 + 52, y + 34, 28, 22, "+", true, C_DIVIDER);
}

void drawAll() {
    tft.fillScreen(C_BG);
    drawHeader();
    drawLightSection(0,     "DRAWING ROOM LIGHTS", dash.drOn);
    drawLightSection(DIV_X, "LAMPS",               dash.lampsOn);
    tft.drawFastVLine(DIV_X, HDR_H, MID_H, C_DIVIDER);
    drawHeatingSection();
}

// ── Touch calibration ───────────────────────────────────────
uint16_t calData[5];

void touchSetup() {
    prefs.begin("tft-cal", false);
    if (prefs.getBool("calibrated", false)) {
        prefs.getBytes("caldata", calData, sizeof(calData));
        tft.setTouch(calData);
    } else {
        tft.fillScreen(TFT_BLACK);
        tft.setTextColor(TFT_WHITE, TFT_BLACK);
        tft.setTextDatum(MC_DATUM);
        tft.setTextSize(2);
        tft.drawString("Touch each marker", SCREEN_W / 2, SCREEN_H / 2 - 16);
        tft.setTextSize(1);
        tft.drawString("Use stylus for accuracy", SCREEN_W / 2, SCREEN_H / 2 + 12);
        delay(2000);
        tft.calibrateTouch(calData, TFT_MAGENTA, TFT_BLACK, 15);
        prefs.putBool("calibrated", true);
        prefs.putBytes("caldata", calData, sizeof(calData));
    }
    prefs.end();
}

// ── Touch hit testing ───────────────────────────────────────
void handleTouch() {
    uint16_t tx, ty;
    if (!tft.getTouch(&tx, &ty)) return;
    delay(80); // simple debounce

    int w    = DIV_X;
    int btnY = HDR_H + MID_H - BTN_H - 10;

    // Drawing room ON
    int drOnX  = 0 + w / 2 - BTN_W - 4;
    int drOffX = 0 + w / 2 + 4;
    if (ty >= btnY && ty <= btnY + BTN_H) {
        if (tx >= drOnX && tx <= drOnX + BTN_W) {
            setDrawingRoomLights(true);
            drawLightSection(0, "DRAWING ROOM LIGHTS", dash.drOn);
            tft.drawFastVLine(DIV_X, HDR_H, MID_H, C_DIVIDER);
            return;
        }
        if (tx >= drOffX && tx <= drOffX + BTN_W) {
            setDrawingRoomLights(false);
            drawLightSection(0, "DRAWING ROOM LIGHTS", dash.drOn);
            tft.drawFastVLine(DIV_X, HDR_H, MID_H, C_DIVIDER);
            return;
        }
        // Lamps ON
        int lampOnX  = DIV_X + w / 2 - BTN_W - 4;
        int lampOffX = DIV_X + w / 2 + 4;
        if (tx >= lampOnX && tx <= lampOnX + BTN_W) {
            setLamps(true);
            drawLightSection(DIV_X, "LAMPS", dash.lampsOn);
            tft.drawFastVLine(DIV_X, HDR_H, MID_H, C_DIVIDER);
            return;
        }
        if (tx >= lampOffX && tx <= lampOffX + BTN_W) {
            setLamps(false);
            drawLightSection(DIV_X, "LAMPS", dash.lampsOn);
            tft.drawFastVLine(DIV_X, HDR_H, MID_H, C_DIVIDER);
            return;
        }
    }

    // Heating buttons
    int htgY = SCREEN_H - HTG_H;
    if (ty >= htgY + 34 && ty <= htgY + 56) {
        if (tx >= SCREEN_W / 2 - 80 && tx <= SCREEN_W / 2 - 52) {
            adjustTemp(-0.5f);
            drawHeatingSection();
            return;
        }
        if (tx >= SCREEN_W / 2 + 52 && tx <= SCREEN_W / 2 + 80) {
            adjustTemp(0.5f);
            drawHeatingSection();
            return;
        }
    }
}

// ── WiFi reconnect ──────────────────────────────────────────
void checkWifi() {
    if (WiFi.status() != WL_CONNECTED) {
        dash.wifiOk = false;
        WiFi.reconnect();
        unsigned long t = millis();
        while (WiFi.status() != WL_CONNECTED && millis() - t < 10000) delay(500);
        dash.wifiOk = (WiFi.status() == WL_CONNECTED);
    }
}

// ── Setup ───────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);

    tft.init();
    tft.setRotation(1);
    tft.fillScreen(TFT_BLACK);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.setTextSize(2);
    tft.drawString("Living Room", SCREEN_W / 2, SCREEN_H / 2 - 20);
    tft.setTextSize(1);
    tft.drawString("Connecting to WiFi...", SCREEN_W / 2, SCREEN_H / 2 + 10);

    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nConnected: " + WiFi.localIP().toString());
    dash.wifiOk = true;

    touchSetup();

    tft.fillScreen(TFT_BLACK);
    tft.setTextSize(1);
    tft.drawString("Loading dashboard...", SCREEN_W / 2, SCREEN_H / 2);

    pollHA();
    drawAll();
}

// ── Loop ────────────────────────────────────────────────────
void loop() {
    handleTouch();

    if (millis() - lastPoll > DASHBOARD_POLL_MS) {
        lastPoll = millis();
        checkWifi();
        pollHA();
        drawAll();
    }
}
