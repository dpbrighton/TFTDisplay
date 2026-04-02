#!/usr/bin/env bash
# ============================================================
# TFT Display Project — Mac Development Setup
# ============================================================
# Run this on any Mac (Mac mini or MacBook Air) to install and
# verify all tools needed to work on the TFTDisplay project.
#
# Usage:
#   chmod +x scripts/setup-macbook.sh
#   ./scripts/setup-macbook.sh
# ============================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
warn() { echo -e "${YELLOW}  ! $1${NC}"; }
fail() { echo -e "${RED}  ✗ $1${NC}"; }
info() { echo -e "  $1"; }

echo ""
echo "============================================"
echo "  TFT Display Project — Mac Setup Audit"
echo "============================================"
echo ""

NEEDS_ACTION=0

# ── Homebrew ────────────────────────────────────────────────
echo "── Homebrew ──"
if command -v brew &>/dev/null; then
    ok "Homebrew installed: $(brew --version | head -1)"
else
    warn "Homebrew not found — installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add to PATH for Apple Silicon
    if [[ -f /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
    ok "Homebrew installed"
    NEEDS_ACTION=1
fi
echo ""

# ── Git ─────────────────────────────────────────────────────
echo "── Git ──"
if command -v git &>/dev/null; then
    ok "Git: $(git --version)"
else
    warn "Git not found — installing via Xcode Command Line Tools..."
    xcode-select --install 2>/dev/null || true
    NEEDS_ACTION=1
fi
echo ""

# ── GitHub CLI ──────────────────────────────────────────────
echo "── GitHub CLI ──"
if command -v gh &>/dev/null; then
    ok "GitHub CLI: $(gh --version | head -1)"
else
    warn "GitHub CLI not found — installing..."
    brew install gh
    ok "GitHub CLI installed: $(gh --version | head -1)"
    NEEDS_ACTION=1
fi
if gh auth status &>/dev/null; then
    ok "GitHub CLI authenticated"
else
    warn "GitHub CLI not authenticated — run: gh auth login"
    NEEDS_ACTION=1
fi
echo ""

# ── Python 3 ────────────────────────────────────────────────
echo "── Python 3 ──"
if command -v python3 &>/dev/null; then
    ok "Python 3: $(python3 --version)"
else
    warn "Python 3 not found — installing via Homebrew..."
    brew install python3
    ok "Python 3 installed: $(python3 --version)"
    NEEDS_ACTION=1
fi
# Check pip
if python3 -m pip --version &>/dev/null; then
    ok "pip: $(python3 -m pip --version | awk '{print $1, $2}')"
else
    warn "pip not available"
    NEEDS_ACTION=1
fi
echo ""

# ── Photo tools virtualenv ───────────────────────────────────
echo "── Photo Orientation Tools (optional) ──"
VENV="$HOME/photo-tools-venv"
if [[ -d "$VENV" ]]; then
    ok "Virtual env exists: $VENV"
    if "$VENV/bin/python" -c "import PIL, cv2, piexif" 2>/dev/null; then
        ok "pillow, opencv-python, piexif all installed in venv"
    else
        warn "Some packages missing from venv — run:"
        info "  source $VENV/bin/activate && pip install pillow opencv-python piexif"
        NEEDS_ACTION=1
    fi
else
    warn "Photo tools venv not found — to set up:"
    info "  python3 -m venv $VENV"
    info "  source $VENV/bin/activate"
    info "  pip install pillow opencv-python piexif"
    info "(Only needed to run audit/fix photo orientation scripts)"
fi
echo ""

# ── VS Code ─────────────────────────────────────────────────
echo "── VS Code ──"
if command -v code &>/dev/null; then
    ok "VS Code CLI available: $(code --version | head -1)"
else
    if [[ -d "/Applications/Visual Studio Code.app" ]]; then
        warn "VS Code installed but 'code' CLI not in PATH"
        info "In VS Code: Cmd+Shift+P → 'Shell Command: Install code in PATH'"
        NEEDS_ACTION=1
    else
        warn "VS Code not found — installing..."
        brew install --cask visual-studio-code
        ok "VS Code installed"
        warn "Add 'code' to PATH: Cmd+Shift+P → 'Shell Command: Install code in PATH'"
        NEEDS_ACTION=1
    fi
fi
echo ""

# ── PlatformIO ──────────────────────────────────────────────
echo "── PlatformIO ──"
if command -v pio &>/dev/null; then
    ok "PlatformIO CLI: $(pio --version)"
elif [[ -f "$HOME/.platformio/penv/bin/pio" ]]; then
    ok "PlatformIO installed (not in PATH — sourced via VS Code)"
    info "To use from terminal: source $HOME/.platformio/penv/bin/activate"
else
    warn "PlatformIO not found"
    info "Install via VS Code:"
    info "  1. Open VS Code"
    info "  2. Extensions (Cmd+Shift+X)"
    info "  3. Search 'PlatformIO IDE' → Install"
    info "Or via pip: pip install platformio"
    NEEDS_ACTION=1
fi
echo ""

# ── Pandoc (optional) ───────────────────────────────────────
echo "── Pandoc (optional — for doc conversion) ──"
if command -v pandoc &>/dev/null; then
    ok "Pandoc: $(pandoc --version | head -1)"
else
    warn "Pandoc not installed (optional)"
    info "Install with: brew install pandoc"
fi
echo ""

# ── SSH access to NAS ───────────────────────────────────────
echo "── NAS SSH access ──"
NAS_IP="192.168.0.248"
if ssh -o ConnectTimeout=3 -o BatchMode=yes -o StrictHostKeyChecking=no \
       Davidadmin@$NAS_IP true 2>/dev/null; then
    ok "SSH key-based access to NAS ($NAS_IP) works"
else
    warn "Cannot SSH to NAS without password"
    info "To set up key-based access (avoids typing password each time):"
    info "  ssh-keygen -t ed25519 -C 'macbook-air'   (if you don't have a key)"
    info "  ssh-copy-id Davidadmin@$NAS_IP"
    NEEDS_ACTION=1
fi
echo ""

# ── Project repo ────────────────────────────────────────────
echo "── Project Repository ──"
REPO_DIR="$HOME/Documents/Claud/TFTDisplay"
if [[ -d "$REPO_DIR/.git" ]]; then
    ok "Repo found at $REPO_DIR"
    cd "$REPO_DIR"
    BRANCH=$(git branch --show-current)
    ok "Current branch: $BRANCH"
    # Check for uncommitted changes
    if [[ -n "$(git status --porcelain)" ]]; then
        warn "Uncommitted changes present — run 'git status' to review"
    else
        ok "Working tree clean"
    fi
else
    warn "Project repo not found at $REPO_DIR"
    info "Clone with:"
    info "  mkdir -p $HOME/Documents/Claud"
    info "  cd $HOME/Documents/Claud"
    info "  git clone https://github.com/dpbrighton/TFTDisplay.git"
    NEEDS_ACTION=1
fi
echo ""

# ── config.h ────────────────────────────────────────────────
echo "── Firmware Config ──"
CONFIG="$REPO_DIR/firmware/include/config.h"
TEMPLATE="$REPO_DIR/firmware/include/config.h.template"
if [[ -f "$CONFIG" ]]; then
    ok "config.h present (excluded from Git — contains credentials)"
else
    warn "config.h missing"
    if [[ -f "$TEMPLATE" ]]; then
        info "Create it from the template:"
        info "  cp $TEMPLATE $CONFIG"
        info "  then fill in WiFi, HA token, MQTT credentials"
    fi
    NEEDS_ACTION=1
fi
echo ""

# ── Summary ─────────────────────────────────────────────────
echo "============================================"
if [[ $NEEDS_ACTION -eq 0 ]]; then
    echo -e "${GREEN}  All checks passed — ready to develop!${NC}"
else
    echo -e "${YELLOW}  Some items need attention (see above).${NC}"
fi
echo "============================================"
echo ""
