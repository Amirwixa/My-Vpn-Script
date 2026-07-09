#!/usr/bin/env python3
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

BASE_DIR = "/etc/backhaul-manager"
CONFIG_DIR = os.path.join(BASE_DIR, "configs")
REGISTRY_FILE = os.path.join(BASE_DIR, "tunnels.json")
BIN_DIR = "/usr/local/bin/backhaul"
BIN_PATH = os.path.join(BIN_DIR, "backhaul")
VERSION_FILE = os.path.join(BIN_DIR, ".version")
SYSTEMD_DIR = "/etc/systemd/system"
CERT_DIR = "/etc/backhaul-manager/certs"

GITHUB_REPO = "Musixal/Backhaul"
FALLBACK_VERSION = "v0.6.6"

TRANSPORTS = ["tcp", "tcpmux", "ws", "wss", "wsmux", "wssmux", "udp"]
TRANSPORT_LABELS = {
    "tcp": "TCP",
    "tcpmux": "TCP Mux",
    "ws": "WebSocket",
    "wss": "WebSocket Secure (TLS)",
    "wsmux": "WebSocket Mux",
    "wssmux": "WebSocket Secure Mux",
    "udp": "UDP",
}

MUX_TRANSPORTS = {"tcpmux", "wsmux", "wssmux"}
WS_TRANSPORTS = {"ws", "wss", "wsmux", "wssmux"}
TLS_TRANSPORTS = {"wss", "wssmux"}

class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    PINK = "\033[38;5;205m"

def clear_screen():
    os.system("clear" if os.name != "nt" else "cls")

def banner(title):
    clear_screen()
    print(f"{C.GREEN}Backhaul Manager — {title}{C.RESET}")
    print(f"{C.YELLOW}{'═' * 50}{C.RESET}")

def err(msg): print(f"{C.RED}Error: {msg}{C.RESET}")
def ok(msg): print(f"{C.GREEN}✔ {msg}{C.RESET}")
def warn(msg): print(f"{C.YELLOW}⚠ {msg}{C.RESET}")
def info(msg): print(f"{C.CYAN}ℹ {msg}{C.RESET}")

def prompt_str(label, default=None, required=True):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{C.YELLOW}{label}{suffix}: {C.RESET}").strip()
        if not raw and default is not None: return default
        if not raw and required: continue
        return raw

def prompt_int(label, default=None, min_val=None, max_val=None):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{C.YELLOW}{label}{suffix}: {C.RESET}").strip()
        if not raw and default is not None: return default
        if raw.lstrip("-").isdigit():
            val = int(raw)
            if (min_val is None or val >= min_val) and (max_val is None or val <= max_val):
                return val
        warn("Invalid input.")

def prompt_yes_no(label, default=False):
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        raw = input(f"{C.YELLOW}{label}{suffix}: {C.RESET}").strip().lower()
        if not raw: return default
        if raw in ("y", "yes"): return True
        if raw in ("n", "no"): return False

def prompt_choice(label, options, allow_back=True):
    while True:
        print(f"\n{label}")
        for key, desc in options: print(f"  {C.GREEN}{key}{C.RESET}) {desc}")
        if allow_back: print(f"  {C.RED}0{C.RESET}) Back")
        raw = input(f"{C.PINK}Selection: {C.RESET}").strip()
        if allow_back and raw == "0": return None
        if any(str(k) == raw for k, _ in options): return raw
        warn("Invalid option.")

def run(cmd, check=False, capture=False):
    return subprocess.run(cmd, shell=isinstance(cmd, str), check=check, 
                          stdout=subprocess.PIPE if capture else None, 
                          stderr=subprocess.PIPE if capture else None, text=True)

def ensure_dirs():
    for d in (BASE_DIR, CONFIG_DIR, BIN_DIR, CERT_DIR): os.makedirs(d, exist_ok=True)

def load_registry():
    ensure_dirs()
    if not os.path.exists(REGISTRY_FILE): return []
    try:
        with open(REGISTRY_FILE, "r") as f: return json.load(f)
    except: return []

def save_registry(tunnels):
    with open(REGISTRY_FILE, "w") as f: json.dump(tunnels, f, indent=2)

def install_prerequisites():
    info("Updating packages...")
    run(["apt-get", "update", "-y"])
    run(["apt-get", "install", "-y", "wget", "curl", "tar", "openssl", "tcpdump"])

def download_binary(force=False):
    ensure_dirs()
    target_version = get_latest_version()
    if not force and os.path.exists(BIN_PATH): return
    
    arch = "amd64" if platform.machine() == "x86_64" else "arm64"
    asset = f"backhaul_linux_{arch}.tar.gz"
    url = f"https://github.com/{GITHUB_REPO}/releases/download/{target_version}/{asset}"
    
    info(f"Downloading {asset}...")
    urllib.request.urlretrieve(url, f"/tmp/{asset}")
    shutil.unpack_archive(f"/tmp/{asset}", BIN_DIR)
    os.chmod(BIN_PATH, 0o755)
    with open(VERSION_FILE, "w") as f: f.write(target_version)
    ok("Binary installed.")

def get_latest_version():
    try:
        with urllib.request.urlopen(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest", timeout=5) as r:
            return json.loads(r.read().decode())["tag_name"]
    except: return FALLBACK_VERSION

def write_toml(path, section, config):
    lines = [f"[{section}]"]
    for k, v in config.items():
        if k == "ports":
            lines.append("ports = [")
            for p in v: lines.append(f'    "{p}",')
            lines.append("]")
        else:
            lines.append(f'{k} = {"true" if v else "false" if isinstance(v, bool) else v if isinstance(v, int) else f"{v}"}')
    with open(path, "w") as f: f.write("\n".join(lines) + "\n")

def create_tunnel_service(name, config_path):
    svc = f"[Unit]\nDescription=Backhaul {name}\n[Service]\nExecStart={BIN_PATH} -c {config_path}\nRestart=always\n[Install]\nWantedBy=multi-user.target"
    path = os.path.join(SYSTEMD_DIR, f"backhaul-{name}.service")
    with open(path, "w") as f: f.write(svc)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "--now", f"backhaul-{name}"])
    return f"backhaul-{name}.service"

def create_tunnel_flow(role):
    banner("Create New Tunnel")
    name = prompt_str("Unique tunnel name")
    transport = TRANSPORTS[int(prompt_choice("Transport:", [(str(i+1), TRANSPORT_LABELS[t]) for i, t in enumerate(TRANSPORTS)]))-1]
    
    config = {}
    if role == "server":
        config = {"bind_addr": f"0.0.0.0:{prompt_int('Bind Port', default=8443)}", "transport": transport, "token": prompt_str("Token")}
        if transport != "udp": config["ports"] = [prompt_str("Port rule (e.g., 8080=80)")]
    else:
        config = {"remote_addr": f"{prompt_str('Remote Address')}:{prompt_int('Remote Port')}", "transport": transport, "token": prompt_str("Token")}
    
    config_path = os.path.join(CONFIG_DIR, f"{name}.toml")
    write_toml(config_path, role, config)
    svc = create_tunnel_service(name, config_path)
    
    tunnels = load_registry()
    tunnels.append({"name": name, "role": role, "transport": transport, "service_name": svc, "config_path": config_path})
    save_registry(tunnels)
    ok(f"Tunnel {name} created.")
    input("Press Enter...")

def list_tunnels():
    tunnels = load_registry()
    if not tunnels: warn("No tunnels found."); return
    for t in tunnels: print(f"{t['name']} | {t['role']} | Status: {run(['systemctl', 'is-active', t['service_name']], capture=True).stdout.strip()}")
    input("Press Enter...")

def main_menu():
    while True:
        banner("Main Menu")
        choice = prompt_choice("Options:", [("1", "Create Tunnel"), ("2", "List Tunnels"), ("3", "Exit")], allow_back=False)
        if choice == "1": create_tunnel_flow(input("Role (server/client): "))
        elif choice == "2": list_tunnels()
        else: sys.exit()

if __name__ == "__main__":
    if os.geteuid() != 0: err("Run as root."); sys.exit(1)
    ensure_dirs()
    main_menu()
