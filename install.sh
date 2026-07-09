#!/bin/bash
set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run as root."
    exit 1
fi

INSTALL_DIR="/usr/local/lib/backhaul-manager"
BIN_LINK="/usr/local/bin/bhmgr"

# آدرس خام فایل پایتون خودتان
SCRIPT_URL="https://raw.githubusercontent.com/Amirwixa/My-Vpn-Script/refs/heads/main/bhmgr.py"

command -v python3 >/dev/null 2>&1 || {
    echo "Installing python3..."
    apt-get update -y && apt-get install -y python3
}

mkdir -p "$INSTALL_DIR"

echo "Downloading Backhaul Manager..."
curl -fsSL "$SCRIPT_URL" -o "$INSTALL_DIR/bhmgr.py"

# مهم: shebang + مجوز اجرا
chmod +x "$INSTALL_DIR/bhmgr.py"

# symlink
ln -sf "$INSTALL_DIR/bhmgr.py" "$BIN_LINK"

echo "✅ Installation complete!"
echo "Run with:   sudo bhmgr"
