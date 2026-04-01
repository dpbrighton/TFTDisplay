# TFT Living Room Display — Project Documentation

**Version:** 0.8
**Date:** April 2026
**Status:** Phases 1 and 2 complete

---

## 1. Project Overview

A wall-mounted smart display for the living room built around an ESP32 microcontroller and a 3.2" TFT touchscreen. The display serves two purposes:

- **Dashboard mode** — shows the current state of living room lights and heating, with touch controls to turn them on and off
- **Screensaver mode** — after 60 seconds idle, switches to a photo slideshow pulling images from the home NAS

A third phase (Eufy doorbell integration) is planned.

---

## 2. Hardware

| Component | Details |
|---|---|
| Microcontroller | ESP32 WROOM-32 (30-pin DevKit, Type-C USB) |
| Display | 3.2" SPI TFT, ILI9341 driver, 240×320 resolution |
| Screen SKU | MSP3218 |
| Touch | Resistive (XPT2046 controller) — stylus included; large buttons work with finger |
| Connection | Dupont jumper wires |

### 2.1 Wiring

| Screen Pin | ESP32 Pin | Notes |
|---|---|---|
| VCC | 3.3V | |
| GND | GND | |
| CS | GPIO 5 | Display chip select |
| RESET | GPIO 4 | |
| DC | GPIO 16 | **Note: GPIO 2 conflicts with boot — use GPIO 16** |
| SDI (MOSI) | GPIO 23 | |
| SCK | GPIO 18 | Shared with T_CLK |
| LED | VIN (5V) | Backlight — 5V gives good brightness |
| SDO (MISO) | GPIO 19 | Shared with T_DO |
| T_CLK | GPIO 18 | Shared with SCK |
| T_CS | GPIO 15 | Touch chip select |
| T_DIN | GPIO 23 | Shared with MOSI |
| T_DO | GPIO 19 | Shared with MISO |
| T_IRQ | GPIO 21 | Touch interrupt |

> **Important:** GPIO 2 on the ESP32 WROOM-32 is connected to the onboard LED and causes display initialisation to fail if used as the DC pin. Always use GPIO 16 for DC.

> **Shared SPI pins:** SCK/T_CLK, MOSI/T_DIN, and MISO/T_DO all share the same ESP32 pins. Connect both screen wires to the same ESP32 pin (twist wire ends together into one Dupont socket).

---

## 3. System Architecture

```
+---------------------+     WiFi / REST API    +----------------------+
|   ESP32 + TFT       | <--------------------> |  Home Assistant      |
|   Living Room       |                         |  Raspberry Pi 5      |
|   Display           |     WiFi / HTTP         |  192.168.0.38:8123   |
|   192.168.0.103     | <--------------------> +----------------------+
|                     |                         |  NAS Photo Server    |
+---------------------+                         |  Docker on DPX2800   |
                                                 |  192.168.0.248:5000  |
                                                 +----------------------+
```

---

## 4. Software — Development Environment

### 4.1 Mac Toolchain

| Tool | Version | How installed |
|---|---|---|
| Git | 2.50.1 | Apple built-in |
| Homebrew | 5.1.1 | brew.sh |
| Python 3 | 3.14.3 | Homebrew |
| Node.js | 25.8.1 | Homebrew |
| VS Code | 1.113.0 | `brew install --cask visual-studio-code` |
| GitHub CLI | 2.89.0 | `brew install gh` |
| PlatformIO | latest | VS Code extension |
| Pandoc | 3.9.0 | `brew install pandoc` |

> To replicate this setup on the MacBook Air, install each tool using the same method.

### 4.2 Project Repository

- **GitHub:** https://github.com/dpbrighton/TFTDisplay
- **Local path (Mac mini):** `~/Documents/Claud/TFTDisplay`

### 4.3 Version Snapshots

| Tag | Description |
|---|---|
| v0.1-project-start | Initial structure and README |
| v0.2-firmware-skeleton | PlatformIO project, config, basic WiFi + display |
| v0.3-display-working | Fixed DC pin (GPIO 16), display confirmed working |
| v0.4-dashboard-working | Phase 1 complete — HA dashboard live |
| v0.5-dashboard-refined | No-flicker refresh, larger heating buttons |
| v0.6-photo-server-ui | NAS photo server with web UI for folder selection |
| v0.7-screensaver-working | Phase 2 complete — photo screensaver |
| v0.8-photo-orientation | EXIF orientation fix, photo streaming improvements, orientation tools |

---

## 5. ESP32 Firmware

### 5.1 Build Tool

**PlatformIO** (VS Code extension). Open the `firmware/` folder in VS Code. Use the tick button to build and arrow to upload.

### 5.2 Libraries

| Library | Purpose |
|---|---|
| bodmer/TFT_eSPI | Display and touch driver |
| bblanchon/ArduinoJson | Parsing Home Assistant JSON responses |
| knolleary/PubSubClient | MQTT (reserved for Phase 3) |
| bodmer/TJpg_Decoder | JPEG decoding for photo slideshow |

### 5.3 Configuration

Edit `firmware/include/config.h` before flashing. This file is excluded from Git (credentials). Use `config.h.template` as a starting point on a new machine.

| Setting | Description |
|---|---|
| `WIFI_SSID` / `WIFI_PASSWORD` | Home WiFi credentials |
| `HA_HOST` | Home Assistant IP (192.168.0.38) |
| `HA_PORT` | 8123 |
| `HA_TOKEN` | Long-lived access token from HA profile |
| `PHOTO_SERVER_HOST` | NAS IP (192.168.0.248) |
| `PHOTO_SERVER_PORT` | 5000 |
| `DASHBOARD_POLL_MS` | How often to refresh HA state (default 10000ms) |
| `SCREENSAVER_TIMEOUT` | Idle time before screensaver (default 60000ms) |

### 5.4 Touch Calibration

On first boot, the display runs a touch calibration routine — touch each marker with the stylus. Calibration data is saved to the ESP32's non-volatile storage and is not repeated unless the device is erased.

To force recalibration: in Arduino/PlatformIO, erase the flash (`pio run -t erase`) then reflash.

---

## 6. Home Assistant Entities

| Entity ID | Description |
|---|---|
| `light.drawing_room_light_1` | Drawing room overhead light 1 |
| `light.drawing_room_light_2` | Drawing room overhead light 2 |
| `light.drawing_room_light_3` | Drawing room overhead light 3 |
| `light.drawing_room_light_4` | Drawing room overhead light 4 |
| `light.old_lamp` | Living room lamp (smart bulb) |
| `switch.living_room_lamp_socket_1` | Living room lamp socket |
| `climate.living_room` | Living room TRV (Tado) |

---

## 7. NAS Photo Server

### 7.1 Location

- **NAS:** Greenbow DPX2800 at `ournas.local` / `192.168.0.248`
- **Docker management:** Portainer at port 9999
- **Source files on NAS:** `/volume1/docker/nas-server/`
- **Config folder:** `/volume1/docker/tft-config/`
- **Photos root:** `/volume1/Photos`

### 7.2 Docker Setup

The server runs as a Docker container managed by Portainer. Project defined in `nas-server/docker-compose.yml`.

**Volumes mounted into the container:**

| Host path | Container path | Access |
|---|---|---|
| `/volume1/Photos` | `/photos` | Read-only |
| `/volume1/docker/tft-config` | `/config` | Read-write (saves config) |
| `/volume1/docker/nas-server/app.py` | `/app/app.py` | Read-only (live code updates) |

> Mounting `app.py` as a volume means code updates take effect on container restart — no image rebuild needed.

### 7.3 API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Web UI for folder selection and settings |
| `/next-photo` | GET | Returns a random photo as 320×240 JPEG |
| `/settings` | GET | Returns `{"display_seconds": N}` |
| `/health` | GET | Returns photo count and status |
| `/save-config` | POST | Saves new config (called by web UI) |

### 7.4 Configuration Web UI

Open `http://192.168.0.248:5000` in any browser on the local network to:
- Tick/untick photo folders to include
- Set seconds per photo
- Toggle shuffle and include-subfolders
- Preview a photo
- Save and apply immediately

### 7.5 Photo Orientation

The server automatically corrects photos that have EXIF orientation metadata (e.g. photos taken on a modern phone held in portrait). This is handled by `ImageOps.exif_transpose()` in `app.py`.

For older photos and scans with no EXIF orientation data, two one-off utility scripts are provided in `tools/`:

| Script | Purpose |
|---|---|
| `audit_photo_orientation.py` | Scans the photo library and reports how many photos have EXIF orientation, which are already correct, and which are suspect (landscape pixels, no EXIF) |
| `fix_photo_orientation.py` | Uses face detection (OpenCV) to determine the correct orientation of suspect photos and writes an EXIF orientation tag back to the file |

**To run these on a new machine:**

```bash
python3 -m venv ~/photo-tools-venv
source ~/photo-tools-venv/bin/activate
pip install pillow opencv-python piexif

# Audit first
python3 tools/audit_photo_orientation.py /Volumes/Photos

# Dry run fix (no files changed)
python3 tools/fix_photo_orientation.py /Volumes/Photos

# Apply fixes
python3 tools/fix_photo_orientation.py /Volumes/Photos --apply
```

> The NAS must be mounted at `/Volumes/Photos` via SMB before running these scripts.

---

## 8. Dashboard Operation

| Area | Function |
|---|---|
| Top bar | "LIVING ROOM" title + WiFi status dot (green = connected) |
| Left half | Drawing room lights — ON / OFF buttons, status dot |
| Right half | Lamps — ON / OFF buttons, status dot |
| Bottom strip | Heating — current temp (large), target temp, − and + buttons |

- Dashboard polls Home Assistant every 10 seconds
- Only changed sections are redrawn (no flicker)
- Temperature changes made in the Tado app take 1–2 minutes to appear (Tado → HA sync delay)

---

## 9. Screensaver Operation

- After **60 seconds** with no touch, the display switches to photo slideshow
- Photos are fetched from the NAS server, pre-resized to 320×240
- Display duration per photo is set in the NAS web UI
- **Touch anywhere** to return to the dashboard immediately

---

## 10. Planned — Phase 3: Eufy Doorbell

When the doorbell rings:
- Home Assistant (via Eufy integration) detects the event
- HA sends a notification to the ESP32 (via MQTT or webhook)
- The display switches to show a camera snapshot
- Returns to previous mode after a timeout

---

## 11. Known Issues / Notes

- **Tado sync lag:** Temperature changes in Tado app take 1–2 minutes to reflect on the display. This is a Tado–HA sync limitation.
- **Resistive touch:** Large buttons work well with a finger. For precise input use the supplied stylus.
- **Photo server startup:** On NAS reboot, the container scans all selected photo directories before serving. With 18,000+ photos this takes a few seconds.
- **Portrait photos (old/scanned):** Photos taken on modern phones are auto-corrected via EXIF orientation. Older scanned photos without EXIF data were corrected using the `tools/fix_photo_orientation.py` script (face detection). ~167 photos were fixed in the initial run; ~1,449 suspect files were left unchanged as they are likely genuine landscape shots.
