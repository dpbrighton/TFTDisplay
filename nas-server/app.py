"""
TFT Display Photo Server
Runs in Docker on the NAS. Picks random photos, resizes to 320x240 JPEG,
serves them to the ESP32 over HTTP.
"""

import json
import os
import random
from io import BytesIO
from flask import Flask, send_file, jsonify, request

try:
    from PIL import Image, UnidentifiedImageError
except ImportError:
    raise SystemExit("Pillow not installed — rebuild the Docker image")

app = Flask(__name__)

CONFIG_PATH = "/config/photo_config.json"
SCREEN_W    = 320
SCREEN_H    = 240

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "directories":       ["/photos"],
    "display_seconds":   10,
    "shuffle":           True,
    "include_subfolders": True
}

config     = DEFAULT_CONFIG.copy()
file_list  = []

SUPPORTED = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}


def load_config():
    global config
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            config = {**DEFAULT_CONFIG, **json.load(f)}
        print(f"Config loaded: {config}")
    else:
        print(f"No config at {CONFIG_PATH}, using defaults")


def scan_photos():
    global file_list
    found = []
    for directory in config.get("directories", ["/photos"]):
        if not os.path.isdir(directory):
            print(f"Warning: directory not found: {directory}")
            continue
        if config.get("include_subfolders", True):
            for root, _, files in os.walk(directory):
                for f in files:
                    if os.path.splitext(f)[1].lower() in SUPPORTED:
                        found.append(os.path.join(root, f))
        else:
            for f in os.listdir(directory):
                if os.path.splitext(f)[1].lower() in SUPPORTED:
                    found.append(os.path.join(directory, f))

    if config.get("shuffle", True):
        random.shuffle(found)

    file_list = found
    print(f"Found {len(file_list)} photos")


def pick_photo():
    """Return path to a random photo, skipping unreadable files."""
    if not file_list:
        return None
    attempts = min(20, len(file_list))
    for _ in range(attempts):
        path = random.choice(file_list)
        try:
            Image.open(path).verify()
            return path
        except Exception:
            continue
    return None


def image_to_jpeg(path):
    """Open any supported image, resize to fit 320x240, return JPEG bytes."""
    with Image.open(path) as img:
        # Handle animated GIF — use first frame
        if hasattr(img, "n_frames") and img.n_frames > 1:
            img.seek(0)

        img = img.convert("RGB")

        # Scale to fit 320x240 preserving aspect ratio, then centre-crop
        img.thumbnail((SCREEN_W, SCREEN_H), Image.LANCZOS)
        canvas = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
        x = (SCREEN_W - img.width)  // 2
        y = (SCREEN_H - img.height) // 2
        canvas.paste(img, (x, y))

        buf = BytesIO()
        canvas.save(buf, format="JPEG", quality=85, optimize=True)
        buf.seek(0)
        return buf


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/next-photo")
def next_photo():
    path = pick_photo()
    if path is None:
        return jsonify({"error": "No photos available"}), 503
    try:
        buf = image_to_jpeg(path)
        print(f"Serving: {path}")
        return send_file(buf, mimetype="image/jpeg")
    except (UnidentifiedImageError, Exception) as e:
        print(f"Error processing {path}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/config")
def get_config():
    return jsonify({
        "config":      config,
        "photo_count": len(file_list)
    })


@app.route("/reload", methods=["POST"])
def reload():
    load_config()
    scan_photos()
    return jsonify({"status": "ok", "photo_count": len(file_list)})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "photo_count": len(file_list)})


# ── Startup ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    load_config()
    scan_photos()
    app.run(host="0.0.0.0", port=5000, debug=False)
