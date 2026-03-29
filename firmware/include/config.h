#pragma once

// ============================================================
// WiFi
// ============================================================
#define WIFI_SSID     "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

// ============================================================
// Home Assistant
// ============================================================
#define HA_HOST    "homeassistant.local"   // or IP address of your Pi
#define HA_PORT    8123
#define HA_TOKEN   "YOUR_LONG_LIVED_HA_TOKEN"

// Home Assistant entity IDs — update these to match yours
#define ENTITY_LAMPS          "light.living_room_lamps"         // group or scene
#define ENTITY_DRAWING_LIGHTS "light.drawing_room_lights"       // group for lights 1-4
#define ENTITY_TRV            "climate.living_room_trv"

// ============================================================
// NAS Photo Server (Phase 2)
// ============================================================
#define PHOTO_SERVER_HOST "192.168.1.x"   // NAS IP address
#define PHOTO_SERVER_PORT 5000
#define PHOTO_ENDPOINT    "/next-photo"

// ============================================================
// Display timing
// ============================================================
#define DASHBOARD_POLL_MS   10000   // How often to refresh HA state (ms)
#define SCREENSAVER_TIMEOUT 60000   // Idle time before screensaver starts (ms)
