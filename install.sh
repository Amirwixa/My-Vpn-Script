#!/bin/bash
# نصب‌کننده‌ی Backhaul Manager
# استفاده: sudo bash install.sh

set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "لطفاً این اسکریپت را با sudo اجرا کنید."
    exit 1
fi

INSTALL_DIR="/usr/local/lib/backhaul-manager"
BIN_LINK="/usr/local/bin/bhmgr"
SCRIPT_URL="https://raw.githubusercontent.com/Amirwixa/My-Vpn-Script/refs/heads/main/bhmgr.py"

command -v python3 >/dev/null 2>&1 || {
    echo "در حال نصب python3..."
    apt-get update -y && apt-get install -y python3
}

mkdir -p "$INSTALL_DIR"

if [ -f "./bhmgr.py" ]; then
    cp ./bhmgr.py "$INSTALL_DIR/bhmgr.py"
else
    echo "در حال دانلود bhmgr.py..."
    curl -fsSL "$SCRIPT_URL" -o "$INSTALL_DIR/bhmgr.py"
fi

chmod +x "$INSTALL_DIR/bhmgr.py"
ln -sf "$INSTALL_DIR/bhmgr.py" "$BIN_LINK"

echo "نصب کامل شد!"
echo "برای اجرا کافیست دستور زیر را بزنید:"
echo ""
echo "    sudo bhmgr"
echo ""
