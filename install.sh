#!/bin/bash
set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run as root."
    exit 1
fi

INSTALL_DIR="/usr/local/lib/backhaul-manager"
BIN_FILE="/usr/local/bin/bhmgr"
SCRIPT_URL="https://raw.githubusercontent.com/Amirwixa/My-Vpn-Script/refs/heads/main/bhmgr.py"

command -v python3 >/dev/null 2>&1 || {
    apt-get update -y && apt-get install -y python3
}

mkdir -p "$INSTALL_DIR"

echo "Downloading manager..."
curl -fsSL "$SCRIPT_URL" -o "$INSTALL_DIR/bhmgr.py"

# ساخت فایلِ اجراکننده (به جای لینک ساده)
echo '#!/bin/bash' > "$BIN_FILE"
echo 'python3 /usr/local/lib/backhaul-manager/bhmgr.py' >> "$BIN_FILE"
chmod +x "$BIN_FILE"

echo "Installation complete!"
/usr/local/bin/bhmgr
