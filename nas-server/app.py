"""
TFT Display Photo Server
Runs in Docker on the NAS. Picks random photos, resizes to 320x240 JPEG,
serves them to the ESP32 over HTTP.
Includes a web UI at / for configuration.
"""

import json
import os
import random
from io import BytesIO
from flask import Flask, send_file, jsonify, request, render_template_string

try:
    from PIL import Image, UnidentifiedImageError
except ImportError:
    raise SystemExit("Pillow not installed — rebuild the Docker image")

app = Flask(__name__)

CONFIG_PATH = "/config/photo_config.json"
PHOTOS_ROOT = "/photos"
SCREEN_W    = 320
SCREEN_H    = 240

DEFAULT_CONFIG = {
    "directories":        [PHOTOS_ROOT],
    "display_seconds":    10,
    "shuffle":            True,
    "include_subfolders": True
}

config    = DEFAULT_CONFIG.copy()
file_list = []

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

    <button type="button" class="btn" onclick="saveConfig()">Save &amp; Apply</button>
    <button type="button" class="btn btn-secondary" onclick="previewPhoto()">Preview photo</button>
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
        include_subfolders: form.include_subfolders.checked
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
    save_config()
    scan_photos()
    return jsonify({"status": "ok", "photo_count": len(file_list)})


# ── API routes ────────────────────────────────────────────────────────────────

@app.route("/next-photo")
def next_photo():
    path = pick_photo()
    if path is None:
        return jsonify({"error": "No photos available"}), 503
    try:
        return send_file(image_to_jpeg(path), mimetype="image/jpeg")
    except (UnidentifiedImageError, Exception) as e:
        print(f"Error processing {path}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/settings")
def get_settings():
    return jsonify({"display_seconds": config.get("display_seconds", 10)})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "photo_count": len(file_list)})


# ── Startup ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    load_config()
    scan_photos()
    app.run(host="0.0.0.0", port=5000, debug=False)
