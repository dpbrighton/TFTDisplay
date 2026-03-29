# TFT Display Project

An ESP32-based smart display using a 3.2" ILI9341 TFT touchscreen (240×320).

## Hardware

| Component | Details |
|---|---|
| Microcontroller | ESP32 WROOM-32 (30-pin) |
| Display | 3.2" SPI TFT, ILI9341 driver, 240×320, resistive touch |
| Screen SKU | MSP3218 |
| Touch | Resistive — stylus included, large touch targets work with finger |

## Project Phases

### Phase 1 — Home Assistant Dashboard
A simple touch dashboard for the living room:
- **Lamps**: all on / all off (smart bulb + socket)
- **Drawing Room Lights 1–4**: all on / all off
- **Heating**: living room TRV temperature display and control

The ESP32 communicates with Home Assistant (running on Raspberry Pi 5, Home OS) via its REST API over WiFi.

### Phase 2 — Photo Slideshow / Screensaver
A picture-frame style slideshow pulling photos from a Greenbow DPX2800 NAS.

Architecture:
- A Docker container on the NAS runs a Python/Flask photo server
- The server reads a config file (directories to include, display duration, etc.)
- It selects random photos, converts and resizes them to 240×320 JPEG
- The ESP32 fetches pre-processed JPEGs via HTTP — no format conversion needed on-device

Config file (on NAS) controls:
- Which directories/subdirectories to draw from
- How long each photo displays
- Any other display preferences

### Phase 3 — Eufy Doorbell Integration
When the doorbell is pressed:
- Home Assistant (via Eufy integration) triggers the ESP32
- The display switches to show a snapshot from the doorbell camera

## Development Environment

### Mac Setup (Mac mini — primary)

| Tool | Version | Install method |
|---|---|---|
| Git | 2.50.1 | Apple built-in |
| Homebrew | 5.1.1 | brew.sh |
| Python 3 | 3.14.3 | Homebrew |
| Node.js | 25.8.1 | Homebrew |
| VS Code | 1.113.0 | Homebrew cask |
| GitHub CLI | 2.89.0 | Homebrew |
| PlatformIO | — | VS Code extension |

> MacBook Air: install the same tools via Homebrew to keep both machines in sync.

### Firmware Build Tool
**PlatformIO** (VS Code extension) — handles ESP32 compilation, library management, and flashing.

## Version History

| Tag | Description |
|---|---|
| v0.1-project-start | Initial project structure and documentation |

## Repository Structure

```
TFTDisplay/
├── firmware/          # ESP32 PlatformIO project
├── nas-server/        # Docker photo server (Python/Flask)
├── docs/              # Additional documentation
└── README.md
```
