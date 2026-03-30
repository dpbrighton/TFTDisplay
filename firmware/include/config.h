#pragma once

// ============================================================
// WiFi
// ============================================================
#define WIFI_SSID     "BE-49"
#define WIFI_PASSWORD "32Crosslet"

// ============================================================
// Home Assistant
// ============================================================
#define HA_HOST    "192.168.0.38"
#define HA_PORT    8123
#define HA_TOKEN   "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIyOTExZmM1MWU4ZTY0OWQ0YmMwYWNhMzcxMjdlNDJhMSIsImlhdCI6MTc3NDg2NzUyMywiZXhwIjoyMDkwMjI3NTIzfQ.pbE91lwKY8Gqx3wWH-JNsxDiJfTL_xb14_aFAd8Bgv4"

// Home Assistant entity IDs
#define ENTITY_DR_LIGHT_1     "light.drawing_room_light_1"
#define ENTITY_DR_LIGHT_2     "light.drawing_room_light_2"
#define ENTITY_DR_LIGHT_3     "light.drawing_room_light_3"
#define ENTITY_DR_LIGHT_4     "light.drawing_room_light_4"
#define ENTITY_OLD_LAMP       "light.old_lamp"
#define ENTITY_LAMP_SOCKET    "switch.living_room_lamp_socket_1"
#define ENTITY_TRV            "climate.living_room"

// ============================================================
// NAS Photo Server (Phase 2)
// ============================================================
#define PHOTO_SERVER_HOST "192.168.0.248"
#define PHOTO_SERVER_PORT 5000
#define PHOTO_ENDPOINT    "/next-photo"

// ============================================================
// Display timing
// ============================================================
#define DASHBOARD_POLL_MS   10000   // How often to refresh HA state (ms)
#define SCREENSAVER_TIMEOUT 60000   // Idle time before screensaver starts (ms)
