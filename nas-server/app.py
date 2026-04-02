"""
TFT Display Photo Server
Runs in Docker on the NAS. Picks random photos, resizes to 320x240 JPEG,
serves them to the ESP32 over HTTP.
Includes a web UI at / for configuration.
"""

import json
import os
import sys
import random
import threading
import time
import urllib.request
import uuid
from io import BytesIO

sys.stdout.reconfigure(line_buffering=True)  # flush every line — needed in Docker
from flask import Flask, send_file, jsonify, request, render_template_string, Response

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
except ImportError:
    raise SystemExit("Pillow not installed — rebuild the Docker image")

try:
    import websocket as _websocket_lib
    _WS_AVAILABLE = True
except ImportError:
    _WS_AVAILABLE = False
    print("WARNING: websocket-client not installed — eufy WebSocket listener disabled")

app = Flask(__name__)

CONFIG_PATH = "/config/photo_config.json"
PHOTOS_ROOT = "/photos"
SCREEN_W    = 320
SCREEN_H    = 240

DEFAULT_CONFIG = {
    "directories":        [PHOTOS_ROOT],
    "display_seconds":    10,
    "shuffle":            True,
    "include_subfolders": True,
    "ha_host":            "",
    "ha_port":            8123,
    "ha_token":           ""
}

# Doorbell image cache
_doorbell_cache      = None           # JPEG bytes
_doorbell_cache_time = 0              # epoch seconds
DOORBELL_CACHE_TTL   = 120            # seconds before cache expires
_doorbell_picture_ready = threading.Event()  # set when a fresh picture has been cached
HA_DOORBELL_ENTITY   = "image.front_door_bell_event_image"

config    = DEFAULT_CONFIG.copy()
file_list = []

# eufy-security-ws WebSocket listener state
_eufy_ws_thread  = None
_eufy_ws_running = False
_eufy_ws_status  = "not started"   # for diagnostics

SUPPORTED = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}

# ── Config & scanning ─────────────────────────────────────────────────────────

def load_config():
    global config
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            config = {**DEFAULT_CONFIG, **json.load(f)}
    else:
        config = DEFAULT_CONFIG.copy()
    print(f"Config: {config}")


def save_config():
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def scan_photos():
    global file_list
    found = []
    for directory in config.get("directories", [PHOTOS_ROOT]):
        if not os.path.isdir(directory):
            print(f"Warning: not found: {directory}")
            continue
        if config.get("include_subfolders", True):
            for root, _, files in os.walk(directory):
                for fn in files:
                    if os.path.splitext(fn)[1].lower() in SUPPORTED:
                        found.append(os.path.join(root, fn))
        else:
            for fn in os.listdir(directory):
                if os.path.splitext(fn)[1].lower() in SUPPORTED:
                    found.append(os.path.join(directory, fn))
    if config.get("shuffle", True):
        random.shuffle(found)
    file_list = found
    print(f"Found {len(file_list)} photos")


def get_folder_tree(path, depth=0, max_depth=3):
    """Return list of (display_path, full_path, photo_count) for each subdir."""
    folders = []
    try:
        entries = sorted(os.scandir(path), key=lambda e: e.name.lower())
    except PermissionError:
        return folders
    for entry in entries:
        if entry.is_dir(follow_symlinks=False):
            full = entry.path
            count = sum(
                1 for _, _, files in os.walk(full)
                for fn in files
                if os.path.splitext(fn)[1].lower() in SUPPORTED
            )
            display = full.replace(PHOTOS_ROOT, "", 1).lstrip("/") or "(root)"
            folders.append((display, full, count))
            if depth < max_depth:
                folders.extend(get_folder_tree(full, depth + 1, max_depth))
    return folders


def pick_photo():
    if not file_list:
        return None
    for _ in range(min(20, len(file_list))):
        path = random.choice(file_list)
        try:
            Image.open(path).verify()
            return path
        except Exception:
            continue
    return None


def image_to_jpeg(path):
    with Image.open(path) as img:
        if hasattr(img, "n_frames") and img.n_frames > 1:
            img.seek(0)
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.thumbnail((SCREEN_W, SCREEN_H), Image.LANCZOS)
        canvas = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
        x = (SCREEN_W - img.width)  // 2
        y = (SCREEN_H - img.height) // 2
        canvas.paste(img, (x, y))
        buf = BytesIO()
        canvas.save(buf, format="JPEG", quality=85, optimize=True)
        buf.seek(0)
        return buf


# ── Doorbell image ────────────────────────────────────────────────────────────

def fetch_doorbell_from_ha():
    """Fetch the doorbell camera snapshot from HA, resize to 320x240, return JPEG bytes."""
    import datetime
    ha_host  = config.get("ha_host", "")
    ha_port  = config.get("ha_port", 8123)
    ha_token = config.get("ha_token", "")
    if not ha_host or not ha_token:
        print("HA credentials not configured — cannot fetch doorbell image")
        return None

    now = datetime.datetime.now()
    print(f"--- Doorbell fetch at {now.strftime('%H:%M:%S.%f')[:-3]} ---")

    # Query HA entity state to find when it was last updated
    try:
        state_url = f"http://{ha_host}:{ha_port}/api/states/{HA_DOORBELL_ENTITY}"
        state_req = urllib.request.Request(state_url, headers={"Authorization": f"Bearer {ha_token}"})
        with urllib.request.urlopen(state_req, timeout=5) as state_resp:
            state_data = json.loads(state_resp.read())
        entity_state       = state_data.get("state", "unknown")
        entity_last_updated = state_data.get("last_updated", "unknown")
        print(f"  Entity state: {entity_state}")
        print(f"  Entity last_updated: {entity_last_updated}")
    except Exception as e:
        print(f"  Could not query entity state: {e}")

    # Fetch the image
    url = f"http://{ha_host}:{ha_port}/api/image_proxy/{HA_DOORBELL_ENTITY}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {ha_token}"})
    try:
        t0 = datetime.datetime.now()
        with urllib.request.urlopen(req, timeout=10) as resp:
            last_modified = resp.headers.get("Last-Modified", "not provided")
            data = resp.read()
        elapsed = (datetime.datetime.now() - t0).total_seconds()
        print(f"  Image fetch: {len(data)} bytes in {elapsed:.2f}s  Last-Modified: {last_modified}")

        with Image.open(BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            w, h = img.size
            print(f"  Image dimensions: {w}x{h}")
            # T8214 composite: top/bottom layout — crop to top half (main front camera)
            img = img.crop((0, 0, w, h // 2))
            img.thumbnail((SCREEN_W, SCREEN_H), Image.LANCZOS)
            canvas = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
            x = (SCREEN_W - img.width)  // 2
            y = (SCREEN_H - img.height) // 2
            canvas.paste(img, (x, y))
            buf = BytesIO()
            canvas.save(buf, format="JPEG", quality=85, optimize=True)
            result = buf.getvalue()
        print(f"  Output JPEG: {len(result)} bytes")
        print(f"  Total processing time: {(datetime.datetime.now() - now).total_seconds():.2f}s")
        return result
    except Exception as e:
        print(f"  Error fetching doorbell image: {e}")
        return None


# ── eufy-security-ws WebSocket listener ──────────────────────────────────────

def _process_eufy_picture(value):
    """Process a picture value from eufy-security-ws, cache processed JPEG."""
    global _doorbell_cache, _doorbell_cache_time
    import datetime

    image_data = None
    try:
        if isinstance(value, dict):
            if value.get("type") == "Buffer" and "data" in value:
                # Node.js Buffer serialised as {"type":"Buffer","data":[255,216,...]}
                image_data = bytes(value["data"])
                print(f"Eufy WS: picture as Buffer ({len(image_data)} bytes)")
            elif "data" in value and "type" in value:
                # {"type":"image/jpeg","data":[255,216,...]} or {"type":"...","data":{"type":"Buffer","data":[...]}}
                inner = value["data"]
                if isinstance(inner, list):
                    image_data = bytes(inner)
                    print(f"Eufy WS: picture as typed data array ({len(image_data)} bytes, type={value.get('type')})")
                elif isinstance(inner, dict) and inner.get("type") == "Buffer":
                    image_data = bytes(inner["data"])
                    print(f"Eufy WS: picture as nested Buffer ({len(image_data)} bytes)")
                elif isinstance(inner, str):
                    import base64
                    image_data = base64.b64decode(inner)
                    print(f"Eufy WS: picture as typed base64 ({len(image_data)} bytes)")
                else:
                    print(f"Eufy WS: unrecognised data field type: {type(inner)}, keys={list(inner.keys()) if isinstance(inner, dict) else 'n/a'}")
            elif "url" in value:
                url = value["url"]
                print(f"Eufy WS: picture as URL: {url}")
                if url.startswith("file://"):
                    with open(url[7:], "rb") as f:
                        image_data = f.read()
                else:
                    with urllib.request.urlopen(url, timeout=10) as resp:
                        image_data = resp.read()
            else:
                print(f"Eufy WS: unrecognised picture dict keys: {list(value.keys())}")
        elif isinstance(value, str):
            if value.startswith("http"):
                with urllib.request.urlopen(value, timeout=10) as resp:
                    image_data = resp.read()
                print(f"Eufy WS: picture as URL string ({len(image_data)} bytes fetched)")
            else:
                import base64
                image_data = base64.b64decode(value)
                print(f"Eufy WS: picture as base64 ({len(image_data)} bytes)")
        else:
            print(f"Eufy WS: unrecognised picture type: {type(value)}")
    except Exception as e:
        print(f"Eufy WS: error extracting image data: {e}")
        return

    if not image_data:
        print("Eufy WS: no image data extracted — ignoring")
        return

    try:
        with Image.open(BytesIO(image_data)) as img:
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            w, h = img.size
            print(f"Eufy WS: raw image {w}x{h}")
            # T8214 composite: top/bottom layout — crop to top half (main front camera)
            if h > w:
                img = img.crop((0, 0, w, h // 2))
            img.thumbnail((SCREEN_W, SCREEN_H), Image.LANCZOS)
            canvas = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
            x = (SCREEN_W - img.width)  // 2
            y = (SCREEN_H - img.height) // 2
            canvas.paste(img, (x, y))
            buf = BytesIO()
            canvas.save(buf, format="JPEG", quality=85, optimize=True)
            _doorbell_cache      = buf.getvalue()
            _doorbell_cache_time = time.time()
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"Eufy WS: cached {len(_doorbell_cache)} bytes at {ts}")
            _doorbell_picture_ready.set()
    except Exception as e:
        print(f"Eufy WS: error processing image: {e}")


def _eufy_ws_thread_func():
    global _eufy_ws_running, _eufy_ws_status

    while _eufy_ws_running:
        ha_host = config.get("ha_host", "")
        if not ha_host:
            _eufy_ws_status = "waiting — ha_host not configured"
            print("Eufy WS: ha_host not set, retrying in 30s")
            time.sleep(30)
            continue

        ws_url = f"ws://{ha_host}:3000"
        _eufy_ws_status = f"connecting to {ws_url}"
        print(f"Eufy WS: connecting to {ws_url}")

        try:
            ws = _websocket_lib.create_connection(ws_url, timeout=10)
            _eufy_ws_status = "connected"
            print("Eufy WS: connected")

            # Receive the server hello (version message)
            try:
                hello = json.loads(ws.recv())
                print(f"Eufy WS: server hello: {json.dumps(hello)[:200]}")
            except Exception:
                pass

            # Send start_listening
            ws.send(json.dumps({
                "messageId": str(uuid.uuid4()),
                "command":   "start_listening"
            }))
            _eufy_ws_status = "listening"
            print("Eufy WS: sent start_listening")

            ws.settimeout(60)   # recv blocks up to 60s, then we send a ping

            while _eufy_ws_running:
                try:
                    raw = ws.recv()
                except _websocket_lib.WebSocketTimeoutException:
                    ws.ping()
                    continue

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type")

                # Ignore start_listening result (large state dump)
                if msg_type == "result":
                    print("Eufy WS: received result (start_listening ACK)")
                    continue

                if msg_type != "event":
                    continue

                event = msg.get("event", {})
                source = event.get("source")
                ename  = event.get("event")
                prop   = event.get("name", "")

                # Picture property change
                if source == "device" and ename == "property changed" and prop in ("picture", "pictureUrl"):
                    serial = event.get("serialNumber", "?")
                    print(f"Eufy WS: picture event for {serial} (prop={prop})")
                    _process_eufy_picture(event.get("value"))

                elif source == "device" and ename in ("doorbell ring", "rings"):
                    serial = event.get("serialNumber", "?")
                    print(f"Eufy WS: ring event for {serial}")
                    pic = event.get("picture") or event.get("snapshot")
                    if pic:
                        _process_eufy_picture(pic)

            ws.close()

        except Exception as e:
            _eufy_ws_status = f"error: {e}"
            print(f"Eufy WS: connection error: {e}")
            if _eufy_ws_running:
                print("Eufy WS: reconnecting in 15s")
                time.sleep(15)

    _eufy_ws_status = "stopped"
    print("Eufy WS: thread stopped")


def start_eufy_ws():
    global _eufy_ws_thread, _eufy_ws_running
    if not _WS_AVAILABLE:
        print("Eufy WS: websocket-client not available — skipping")
        return
    _eufy_ws_running = True
    _eufy_ws_thread  = threading.Thread(target=_eufy_ws_thread_func, daemon=True, name="eufy-ws")
    _eufy_ws_thread.start()
    print("Eufy WS: listener thread started")


# ── Web UI ────────────────────────────────────────────────────────────────────

UI_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TFT Photo Server</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }
    h1 { color: #00d4ff; margin-bottom: 4px; font-size: 1.4em; }
    .subtitle { color: #888; margin-bottom: 24px; font-size: 0.9em; }
    .card { background: #16213e; border-radius: 10px; padding: 20px; margin-bottom: 16px; }
    h2 { font-size: 1em; color: #aaa; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 14px; }
    .setting { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
    label { color: #ccc; min-width: 160px; }
    input[type=number] { background: #0f3460; border: 1px solid #444; color: #fff;
                         padding: 6px 10px; border-radius: 6px; width: 80px; font-size: 1em; }
    .folder-list { max-height: 400px; overflow-y: auto; }
    .folder-row { display: flex; align-items: center; gap: 10px; padding: 7px 4px;
                  border-bottom: 1px solid #0f3460; }
    .folder-row:last-child { border-bottom: none; }
    .folder-row input[type=checkbox] { width: 18px; height: 18px; cursor: pointer; accent-color: #00d4ff; }
    .folder-name { flex: 1; font-size: 0.9em; word-break: break-all; }
    .folder-count { color: #666; font-size: 0.8em; white-space: nowrap; }
    .indent-1 { padding-left: 20px; }
    .indent-2 { padding-left: 40px; }
    .indent-3 { padding-left: 60px; }
    .btn { background: #00d4ff; color: #000; border: none; padding: 12px 30px;
           border-radius: 8px; font-size: 1em; font-weight: bold; cursor: pointer; }
    .btn:hover { background: #00b8d9; }
    .btn-secondary { background: #0f3460; color: #eee; margin-left: 10px; }
    .btn-secondary:hover { background: #1a4a8a; }
    .status { margin-top: 12px; padding: 10px; border-radius: 6px; font-size: 0.9em; display: none; }
    .status.ok  { background: #1a3d2b; color: #4caf50; display: block; }
    .status.err { background: #3d1a1a; color: #f44336; display: block; }
    .toggle { position: relative; display: inline-block; width: 44px; height: 24px; }
    .toggle input { opacity: 0; width: 0; height: 0; }
    .slider { position: absolute; inset: 0; background: #444; border-radius: 24px; cursor: pointer; transition: .3s; }
    .slider:before { content: ""; position: absolute; height: 18px; width: 18px; left: 3px; bottom: 3px;
                     background: white; border-radius: 50%; transition: .3s; }
    input:checked + .slider { background: #00d4ff; }
    input:checked + .slider:before { transform: translateX(20px); }
    .select-btns { margin-bottom: 10px; }
    .select-btns button { background: none; border: 1px solid #444; color: #aaa; padding: 4px 10px;
                          border-radius: 4px; cursor: pointer; font-size: 0.8em; margin-right: 6px; }
    .select-btns button:hover { border-color: #00d4ff; color: #00d4ff; }
  </style>
</head>
<body>
  <h1>TFT Photo Server</h1>
  <p class="subtitle">{{ photo_count }} photos active &nbsp;|&nbsp; {{ total_folders }} folders available</p>

  <form id="configForm">

    <div class="card">
      <h2>Display Settings</h2>
      <div class="setting">
        <label>Seconds per photo</label>
        <input type="number" name="display_seconds" value="{{ config.display_seconds }}" min="3" max="300">
      </div>
      <div class="setting">
        <label>Shuffle photos</label>
        <label class="toggle">
          <input type="checkbox" name="shuffle" {% if config.shuffle %}checked{% endif %}>
          <span class="slider"></span>
        </label>
      </div>
      <div class="setting">
        <label>Include subfolders</label>
        <label class="toggle">
          <input type="checkbox" name="include_subfolders" {% if config.include_subfolders %}checked{% endif %}>
          <span class="slider"></span>
        </label>
      </div>
    </div>

    <div class="card">
      <h2>Photo Folders</h2>
      <div class="select-btns">
        <button type="button" onclick="selectAll()">Select all</button>
        <button type="button" onclick="selectNone()">Select none</button>
      </div>
      <div class="folder-list">
        {% for display, full, count in folders %}
        {% set depth = display.count('/') %}
        <div class="folder-row indent-{{ depth if depth <= 3 else 3 }}">
          <input type="checkbox" name="directories" value="{{ full }}"
                 {% if full in config.directories %}checked{% endif %}>
          <span class="folder-name">{{ display }}</span>
          <span class="folder-count">{{ count }} photos</span>
        </div>
        {% endfor %}
      </div>
    </div>

    <div class="card">
      <h2>Home Assistant (Doorbell)</h2>
      <div class="setting">
        <label>HA Host</label>
        <input type="text" name="ha_host" value="{{ config.ha_host }}" placeholder="192.168.0.38" style="width:160px;background:#0f3460;border:1px solid #444;color:#fff;padding:6px 10px;border-radius:6px;font-size:1em;">
      </div>
      <div class="setting">
        <label>HA Port</label>
        <input type="number" name="ha_port" value="{{ config.ha_port }}">
      </div>
      <div class="setting">
        <label>HA Token</label>
        <input type="password" name="ha_token" placeholder="{{ 'Token set' if config.ha_token else 'Not set — paste token here' }}" style="width:220px;background:#0f3460;border:1px solid #444;color:#fff;padding:6px 10px;border-radius:6px;font-size:1em;">
      </div>
      <p style="color:#666;font-size:0.8em;margin-top:8px;">Token is write-only. Leave blank to keep existing value.</p>
    </div>

    <button type="button" class="btn" onclick="saveConfig()">Save &amp; Apply</button>
    <button type="button" class="btn btn-secondary" onclick="previewPhoto()">Preview photo</button>
    <button type="button" class="btn btn-secondary" onclick="previewDoorbell()">Preview doorbell</button>
    <div id="status" class="status"></div>

  </form>

  <script>
    function selectAll()  { document.querySelectorAll('[name=directories]').forEach(c => c.checked = true); }
    function selectNone() { document.querySelectorAll('[name=directories]').forEach(c => c.checked = false); }

    function saveConfig() {
      const form = document.getElementById('configForm');
      const dirs = [...form.querySelectorAll('[name=directories]:checked')].map(c => c.value);
      const data = {
        directories:        dirs.length ? dirs : ["/photos"],
        display_seconds:    parseInt(form.display_seconds.value) || 10,
        shuffle:            form.shuffle.checked,
        include_subfolders: form.include_subfolders.checked,
        ha_host:            form.ha_host.value.trim(),
        ha_port:            parseInt(form.ha_port.value) || 8123,
        ha_token:           form.ha_token.value.trim()
      };
      fetch('/save-config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
      })
      .then(r => r.json())
      .then(d => {
        const el = document.getElementById('status');
        el.className = 'status ok';
        el.textContent = `Saved. ${d.photo_count} photos now active.`;
        document.querySelector('.subtitle').textContent =
          `${d.photo_count} photos active | {{ total_folders }} folders available`;
      })
      .catch(() => {
        const el = document.getElementById('status');
        el.className = 'status err';
        el.textContent = 'Error saving — check server logs.';
      });
    }

    function previewPhoto() {
      window.open('/next-photo?t=' + Date.now(), '_blank');
    }

    function previewDoorbell() {
      window.open('/doorbell-snapshot?t=' + Date.now(), '_blank');
    }
  </script>
</body>
</html>
"""

@app.route("/")
def ui():
    folders = get_folder_tree(PHOTOS_ROOT)
    return render_template_string(
        UI_TEMPLATE,
        config=config,
        folders=folders,
        photo_count=len(file_list),
        total_folders=len(folders)
    )


@app.route("/save-config", methods=["POST"])
def save_config_route():
    global config
    data = request.get_json()
    config["directories"]        = data.get("directories", [PHOTOS_ROOT])
    config["display_seconds"]    = int(data.get("display_seconds", 10))
    config["shuffle"]            = bool(data.get("shuffle", True))
    config["include_subfolders"] = bool(data.get("include_subfolders", True))
    config["ha_host"]            = data.get("ha_host", config.get("ha_host", ""))
    config["ha_port"]            = int(data.get("ha_port", 8123))
    # Only update token if a new one was provided
    new_token = data.get("ha_token", "").strip()
    if new_token:
        config["ha_token"] = new_token
    save_config()
    scan_photos()
    return jsonify({"status": "ok", "photo_count": len(file_list)})


# ── API routes ────────────────────────────────────────────────────────────────

def jpeg_response(buf):
    """Return a JPEG with explicit Content-Length and Connection: close.
    Connection: close causes the TCP connection to close after the response,
    which flushes all data immediately and lets the ESP32 detect end-of-stream
    reliably without relying on Content-Length alone."""
    data = buf.read() if hasattr(buf, 'read') else buf
    resp = Response(data, mimetype="image/jpeg")
    resp.headers["Content-Length"] = len(data)
    resp.headers["Connection"] = "close"
    return resp


@app.route("/next-photo")
def next_photo():
    path = pick_photo()
    if path is None:
        return jsonify({"error": "No photos available"}), 503
    try:
        return jpeg_response(image_to_jpeg(path))
    except (UnidentifiedImageError, Exception) as e:
        print(f"Error processing {path}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/settings")
def get_settings():
    return jsonify({"display_seconds": config.get("display_seconds", 10)})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "photo_count": len(file_list)})


@app.route("/test-doorbell")
def test_doorbell():
    """Diagnostic endpoint — returns details of HA connection attempt."""
    ha_host  = config.get("ha_host", "")
    ha_port  = config.get("ha_port", 8123)
    ha_token = config.get("ha_token", "")
    if not ha_host or not ha_token:
        return jsonify({"error": "credentials not set", "ha_host": ha_host, "token_set": bool(ha_token)})
    url = f"http://{ha_host}:{ha_port}/api/image_proxy/{HA_DOORBELL_ENTITY}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {ha_token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            size = len(resp.read())
            return jsonify({"status": resp.status, "bytes": size, "url": url})
    except urllib.error.HTTPError as e:
        return jsonify({"http_error": e.code, "reason": e.reason, "url": url})
    except Exception as e:
        return jsonify({"error": str(e), "url": url})


@app.route("/doorbell-snapshot")
def doorbell_snapshot():
    import datetime
    now_str = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
    print(f"=== /doorbell-snapshot request at {now_str} ===")

    global _doorbell_cache

    # Signal we want a fresh picture, then wait for the WebSocket thread to deliver one
    _doorbell_picture_ready.clear()
    print("  Waiting for fresh picture from eufy-ws (up to 60s)...")
    _doorbell_picture_ready.wait(timeout=60)

    if _doorbell_picture_ready.is_set() and _doorbell_cache:
        data = _doorbell_cache
        _doorbell_cache = None          # consumed — next request waits for a new picture
        _doorbell_picture_ready.clear()
        print(f"  Serving fresh eufy-ws picture ({len(data)} bytes)")
        return jpeg_response(data)

    # Fallback: picture didn't arrive in time — fetch live from HA
    print("  No eufy-ws picture in time — fetching live from HA")
    data = fetch_doorbell_from_ha()
    if data:
        return jpeg_response(data)
    return jsonify({"error": "No doorbell image available — check HA credentials in settings"}), 503


@app.route("/eufy-ws-status")
def eufy_ws_status():
    """Diagnostic: current WebSocket listener state and cache info."""
    import datetime
    cache_age = time.time() - _doorbell_cache_time if _doorbell_cache else None
    return jsonify({
        "ws_status":     _eufy_ws_status,
        "ws_available":  _WS_AVAILABLE,
        "cache_bytes":   len(_doorbell_cache) if _doorbell_cache else 0,
        "cache_age_s":   round(cache_age, 1) if cache_age is not None else None,
        "cache_fresh":   bool(_doorbell_cache and cache_age < DOORBELL_CACHE_TTL)
    })


@app.route("/cache-doorbell-snapshot", methods=["POST"])
def cache_doorbell_snapshot():
    """Called by HA automation to pre-fetch the doorbell image before ESP32 requests it."""
    global _doorbell_cache, _doorbell_cache_time
    data = fetch_doorbell_from_ha()
    if data:
        _doorbell_cache      = data
        _doorbell_cache_time = time.time()
        print("Doorbell image cached")
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "detail": "fetch failed"}), 500


# ── Startup ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    load_config()
    scan_photos()
    start_eufy_ws()
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
