# TFT Display Project

An ESP32-based smart living room display with a 3.2" ILI9341 TFT touchscreen.

## Hardware

| Component | Details |
|---|---|
| Microcontroller | ESP32 WROOM-32 (30-pin) |
| Display | 3.2" SPI TFT, ILI9341 driver, 240×320, resistive touch |
| Screen SKU | MSP3218 |
| Touch | Resistive — stylus included, large touch targets work with finger |

## Project Phases

### Phase 1 — Home Assistant Dashboard ✓
A touch dashboard for the living room:
- **Lamps**: all on / all off (smart bulb + socket)
- **Drawing Room Lights 1–4**: all on / all off
- **Heating**: living room TRV temperature display and ±0.5°C control

### Phase 2 — Photo Slideshow / Screensaver ✓
After 60 seconds idle, switches to a full-screen photo slideshow:
- Docker container on UGREEN NAS serves random photos pre-resized to 320×240
- Web UI at `http://192.168.0.248:5000` for folder selection and timing
- Touch anywhere to return to dashboard

### Phase 3 — Eufy Doorbell Integration ✓
When the doorbell rings:
- MQTT message triggers the ESP32 instantly — shows "Image loading..."
- NAS connects directly to eufy-security-ws (local WebSocket, port 3000) to receive the camera snapshot
- Image is cropped, resized and sent to the ESP32 — displayed full-screen
- Auto-dismisses after 60 seconds or on touch

## Development Environment

### Mac Setup

| Tool | Version | Install method |
|---|---|---|
| Git | 2.50.1 | Apple built-in |
| Homebrew | 5.1.1 | brew.sh |
| Python 3 | 3.14.3 | Homebrew |
| VS Code | 1.113.0 | Homebrew cask |
| GitHub CLI | 2.89.0 | Homebrew |
| PlatformIO | — | VS Code extension |

Run `scripts/setup-macbook.sh` to install and verify all tools on a new Mac.

### Firmware Build Tool
**PlatformIO** (VS Code extension) — handles ESP32 compilation, library management, and flashing.

## Version History

| Tag | Description |
|---|---|
| v0.1-project-start | Initial project structure and documentation |
| v0.4-dashboard-working | Phase 1 complete — HA dashboard live |
| v0.7-screensaver-working | Phase 2 complete — photo screensaver |
| v0.9-doorbell-working | Phase 3 complete — Eufy doorbell integration |

## Repository Structure

```
TFTDisplay/
├── firmware/          # ESP32 PlatformIO project
│   ├── src/main.cpp
│   ├── include/config.h.template
│   └── platformio.ini
├── nas-server/        # Docker photo + doorbell server (Python/Flask)
│   ├── app.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── docker-compose.yml
├── docs/              # Full project documentation
├── scripts/           # Setup and utility scripts
└── README.md
```

See `docs/project-documentation.md` for full wiring, configuration, and operational details.
