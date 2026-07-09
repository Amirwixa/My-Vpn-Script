#!/bin/bash
set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run as root."
    exit 1
fi

INSTALL_DIR="/usr/local/lib/backhaul-manager"
BIN_LINK="/usr/local/bin/bhmgr"
SCRIPT_URL="https://raw.githubusercontent.com/Amirwixa/My-Vpn-Script/refs/heads/main/bhmgr.py"

command -v python3 >/dev/null 2>&1 || {
    apt-get update -y && apt-get install -y python3
}

mkdir -p "$INSTALL_DIR"

curl -fsSL "$SCRIPT_URL" -o "$INSTALL_DIR/bhmgr.py"

chmod +x "$INSTALL_DIR/bhmgr.py"
ln -sf "$INSTALL_DIR/bhmgr.py" "$BIN_LINK"

/usr/local/bin/bhmgr
