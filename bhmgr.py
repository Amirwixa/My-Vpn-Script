#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
FALLBACK_VERSION = "v0.7.0"

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
UDP_OVER_TCP_ELIGIBLE = {"tcp", "tcpmux", "ws", "wss", "wsmux", "wssmux"}


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"
    PINK = "\033[38;5;205m"


def clear_screen():
    os.system("clear" if os.name != "nt" else "cls")


def hr(char="─", width=45, color=C.YELLOW):
    print(f"{color}{char * width}{C.RESET}")


def banner(title):
    clear_screen()
    print(f"{C.GREEN} ^ ^{C.RESET}")
    print(f"{C.GREEN}({C.RED}O,O{C.GREEN}){C.RESET}")
    print(f"{C.GREEN}(   ) {C.GREEN}Backhaul {C.YELLOW}Manager {C.WHITE}— {title}{C.RESET}")
    print(f'{C.GREEN} "-"{C.YELLOW}{"═" * 46}{C.RESET}')


def ok(msg):
    print(f"{C.GREEN}✔ {msg}{C.RESET}")


def err(msg):
    print(f"{C.RED}✘ Error: {msg}{C.RESET}")


def warn(msg):
    print(f"{C.YELLOW}⚠ {msg}{C.RESET}")


def info(msg):
    print(f"{C.CYAN}ℹ {msg}{C.RESET}")


def pause():
    try:
        input(f"\n{C.GRAY}Press Enter to continue...{C.RESET}")
    except (KeyboardInterrupt, EOFError):
        pass


def prompt_str(label, default=None, required=True, secret=False):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        try:
            raw = input(f"{C.YELLOW}{label}{suffix}: {C.RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            raise
        if not raw and default is not None:
            return default
        if not raw and not required:
            return ""
        if not raw and required:
            warn("This field cannot be empty.")
            continue
        return raw


def prompt_int(label, default=None, min_val=None, max_val=None):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{C.YELLOW}{label}{suffix}: {C.RESET}").strip()
        if not raw and default is not None:
            return default
        if not raw.lstrip("-").isdigit():
            warn("Please enter a valid number.")
            continue
        val = int(raw)
        if min_val is not None and val < min_val:
            warn(f"Value must be at least {min_val}.")
            continue
        if max_val is not None and val > max_val:
            warn(f"Value must be at most {max_val}.")
            continue
        return val


def prompt_port(label, default=None):
    return prompt_int(label, default=default, min_val=1, max_val=65535)


def prompt_yes_no(label, default=False):
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        raw = input(f"{C.YELLOW}{label}{suffix}: {C.RESET}").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        warn("Please enter y or n.")


def prompt_choice(label, options, allow_back=True):
    while True:
        print(f"{C.YELLOW}╭{'─' * 44}╮{C.RESET}")
        print(f"{C.YELLOW}{label}{C.RESET}")
        for key, desc in options:
            print(f"  {C.GREEN}{key}{C.RESET})  {desc}")
        if allow_back:
            print(f"  {C.BLUE}0{C.RESET})  Back")
        print(f"{C.YELLOW}╰{'─' * 44}╯{C.RESET}")
        raw = input(f"{C.PINK}Your choice: {C.RESET}").strip()
        if allow_back and raw == "0":
            return None
        valid_keys = [str(k) for k, _ in options]
        if raw in valid_keys:
            for k, _ in options:
                if str(k) == raw:
                    return k
        warn("Invalid option, please try again.")


def require_root():
    if os.geteuid() != 0:
        err("This program must be run as root. Please run it with sudo:")
        print(f"{C.WHITE}sudo bhmgr{C.RESET}")
        sys.exit(1)


def run(cmd, check=False, capture=False):
    try:
        result = subprocess.run(
            cmd, shell=isinstance(cmd, str), check=check,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            text=True,
        )
        return result
    except subprocess.CalledProcessError as e:
        err(f"Command failed: {cmd}\n{e}")
        return e
    except FileNotFoundError:
        err(f"Command not found: {cmd}")
        return None


def ensure_dirs():
    for d in (BASE_DIR, CONFIG_DIR, BIN_DIR, CERT_DIR):
        os.makedirs(d, exist_ok=True)


def load_registry():
    ensure_dirs()
    if not os.path.exists(REGISTRY_FILE):
        return []
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        warn("Registry file was corrupted, a new one will be created.")
        backup = REGISTRY_FILE + f".broken.{int(time.time())}"
        try:
            shutil.copy(REGISTRY_FILE, backup)
            warn(f"Corrupted copy kept at {backup}.")
        except OSError:
            pass
        return []


def save_registry(tunnels):
    ensure_dirs()
    tmp = REGISTRY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tunnels, f, ensure_ascii=False, indent=2)
    os.replace(tmp, REGISTRY_FILE)


def find_tunnel(name):
    for t in load_registry():
        if t["name"] == name:
            return t
    return None


def name_exists(name):
    return find_tunnel(name) is not None


def add_tunnel(entry):
    tunnels = load_registry()
    tunnels.append(entry)
    save_registry(tunnels)


def update_tunnel(name, **fields):
    tunnels = load_registry()
    for t in tunnels:
        if t["name"] == name:
            t.update(fields)
            break
    save_registry(tunnels)


def remove_tunnel_entry(name):
    tunnels = load_registry()
    tunnels = [t for t in tunnels if t["name"] != name]
    save_registry(tunnels)


def unique_service_name(name):
    return f"backhaul-{name}.service"


def unique_timer_name(name):
    return f"backhaul-{name}-reset.timer"


def unique_timer_service_name(name):
    return f"backhaul-{name}-reset.service"


def install_prerequisites():
    system = platform.system()
    if system == "Linux":
        info("Updating package lists...")
        run(["apt-get", "update", "-y"])
        info("Installing wget, curl, tar, openssl, tcpdump...")
        run(["apt-get", "install", "-y", "wget", "curl", "tar", "openssl", "tcpdump"])
    elif system == "Darwin":
        run(["brew", "install", "wget", "curl", "gnu-tar", "openssl"])
    else:
        err("This operating system is not supported.")
        sys.exit(1)


def get_latest_version():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "bhmgr"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            tag = data.get("tag_name")
            if tag:
                return tag
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        pass
    warn(f"Could not fetch the latest version, falling back to {FALLBACK_VERSION}.")
    return FALLBACK_VERSION


def installed_version():
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE) as f:
            return f.read().strip()
    return None


def download_binary(force_update=False):
    ensure_dirs()
    os_name = platform.system().lower()
    arch = platform.machine()

    arch_map = {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
    mapped_arch = arch_map.get(arch)
    if os_name not in ("linux", "darwin") or not mapped_arch:
        err(f"Unsupported OS/architecture: {os_name}/{arch}")
        sys.exit(1)

    target_version = get_latest_version()
    current_version = installed_version()

    if os.path.exists(BIN_PATH) and current_version == target_version and not force_update:
        ok(f"Backhaul binary version {current_version} is already installed.")
        return

    if os.path.exists(BIN_PATH) and current_version and current_version != target_version:
        info(f"Current version: {current_version} → new version available: {target_version}")
        if not prompt_yes_no("Update the binary now?", default=True):
            return

    asset = f"backhaul_{os_name}_{mapped_arch}.tar.gz"
    url = f"https://github.com/{GITHUB_REPO}/releases/download/{target_version}/{asset}"
    tmp_file = f"/tmp/{asset}"

    info(f"Downloading {asset} (version {target_version})...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "bhmgr"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_file, "wb") as out:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 65536
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = int(downloaded / total * 40)
                    sys.stdout.write(f"\r[{'#' * pct}{'.' * (40 - pct)}] {downloaded // 1024} KB")
                    sys.stdout.flush()
        print()
    except urllib.error.URLError as e:
        err(f"Download failed: {e}")
        sys.exit(1)

    info("Extracting binary...")
    extract_dir = f"/tmp/backhaul_extract_{int(time.time())}"
    os.makedirs(extract_dir, exist_ok=True)
    shutil.unpack_archive(tmp_file, extract_dir)

    extracted_bin = None
    for root_dir, _dirs, files in os.walk(extract_dir):
        if "backhaul" in files:
            extracted_bin = os.path.join(root_dir, "backhaul")
            break

    if not extracted_bin:
        err("Could not find the 'backhaul' binary inside the downloaded archive.")
        shutil.rmtree(extract_dir, ignore_errors=True)
        os.remove(tmp_file)
        sys.exit(1)

    staged_bin = BIN_PATH + ".new"
    shutil.copy2(extracted_bin, staged_bin)
    os.chmod(staged_bin, 0o755)
    os.replace(staged_bin, BIN_PATH)
    shutil.rmtree(extract_dir, ignore_errors=True)
    os.remove(tmp_file)

    with open(VERSION_FILE, "w") as f:
        f.write(target_version)
    ok(f"Backhaul binary version {target_version} installed successfully.")

    tunnels = load_registry()
    running = [t for t in tunnels if service_is_active(t["service_name"]) == "active"]
    if running and prompt_yes_no(
            f"Restart {len(running)} running tunnel service(s) to use the new binary?", default=True):
        for t in running:
            run(["systemctl", "restart", t["service_name"]])
            ok(f"Restarted {t['service_name']}.")


def ensure_binary_installed():
    if not os.path.exists(BIN_PATH):
        install_prerequisites()
        download_binary()
    else:
        ok("Backhaul binary is already installed.")


def write_toml(path, section, config):
    lines = [f"[{section}]"]
    for key, value in config.items():
        if key == "ports":
            lines.append("ports = [")
            for p in value:
                lines.append(f'    "{p}",')
            lines.append("]")
        elif isinstance(value, bool):
            lines.append(f'{key} = {"true" if value else "false"}')
        elif isinstance(value, int):
            lines.append(f"{key} = {value}")
        else:
            lines.append(f'{key} = "{value}"')
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def read_toml_simple(path):
    config = {}
    if not os.path.exists(path):
        return config
    in_ports = False
    ports = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("["):
                continue
            if line.startswith("ports"):
                in_ports = True
                continue
            if in_ports:
                if line == "]":
                    in_ports = False
                    config["ports"] = ports
                    continue
                ports.append(line.strip(', "'))
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if v in ("true", "false"):
                    config[k] = v == "true"
                elif v.isdigit():
                    config[k] = int(v)
                else:
                    config[k] = v.strip('"')
    return config


def ask_ports_wizard():
    ports = []
    mode = prompt_choice("Select forward type:", [
        ("1", "Regular port forward"),
        ("2", "Port range forward"),
    ], allow_back=False)

    if mode == "1":
        sub = prompt_choice("Select forward option:", [
            ("1", "Simple forward (local = remote)"),
            ("2", "From a specific local IP"),
            ("3", "To a specific remote IP"),
            ("4", "From a specific local IP to a specific remote IP"),
        ], allow_back=False)

        count = prompt_int("How many ports do you want to forward?", default=1, min_val=1, max_val=200)
        for i in range(1, count + 1):
            if sub == "1":
                local_port = prompt_port(f"Local port #{i}")
                remote_port = prompt_port(f"Remote port #{i}", default=local_port)
                ports.append(f"{local_port}={remote_port}")
            elif sub == "2":
                local_ip = prompt_str(f"Local IP #{i}")
                local_port = prompt_port(f"Local port #{i}")
                remote_port = prompt_port(f"Remote port #{i}", default=local_port)
                ports.append(f"{local_ip}:{local_port}={remote_port}")
            elif sub == "3":
                local_port = prompt_port(f"Local port #{i}")
                remote_ip = prompt_str(f"Remote IP #{i}")
                remote_port = prompt_port(f"Remote port #{i}", default=local_port)
                ports.append(f"{local_port}={remote_ip}:{remote_port}")
            else:
                local_ip = prompt_str(f"Local IP #{i}")
                local_port = prompt_port(f"Local port #{i}")
                remote_ip = prompt_str(f"Remote IP #{i}")
                remote_port = prompt_port(f"Remote port #{i}", default=local_port)
                ports.append(f"{local_ip}:{local_port}={remote_ip}:{remote_port}")
    else:
        sub = prompt_choice("Select port range forward option:", [
            ("1", "Listen on all ports in the range"),
            ("2", "Forward to a specific port"),
            ("3", "Forward to a specific IP and port"),
        ], allow_back=False)
        port_range = prompt_str("Enter port range (example: 100-900)")
        if not re.match(r"^\d+-\d+$", port_range):
            warn("Range format looks invalid, it will still be saved but please double-check it.")
        if sub == "1":
            ports.append(port_range)
        elif sub == "2":
            remote_port = prompt_port("Remote port")
            ports.append(f"{port_range}:{remote_port}")
        else:
            remote_ip = prompt_str("Remote IP")
            remote_port = prompt_port("Remote port")
            ports.append(f"{port_range}={remote_ip}:{remote_port}")

    return ports


def generate_self_signed_cert(cert_name):
    os.makedirs(CERT_DIR, exist_ok=True)
    key_file = os.path.join(CERT_DIR, f"{cert_name}.key")
    csr_file = os.path.join(CERT_DIR, f"{cert_name}.csr")
    crt_file = os.path.join(CERT_DIR, f"{cert_name}.crt")

    if run(["which", "openssl"], capture=True).returncode != 0:
        err("openssl is not installed. Install it with: apt-get install -y openssl")
        return None, None

    run(["openssl", "genpkey", "-algorithm", "RSA", "-out", key_file,
         "-pkeyopt", "rsa_keygen_bits:2048"], check=True)
    run(["openssl", "req", "-new", "-key", key_file, "-out", csr_file,
         "-subj", f"/C=US/ST=NA/L=NA/O=Backhaul/CN={cert_name}"], check=True)
    run(["openssl", "x509", "-req", "-in", csr_file, "-signkey", key_file,
         "-out", crt_file, "-days", "825"], check=True)
    ok(f"Certificate generated: {crt_file}")
    return crt_file, key_file


def create_tunnel_service(name, config_path):
    service_name = unique_service_name(name)
    content = f"""[Unit]
Description=Backhaul Tunnel ({name})
After=network.target

[Service]
Type=simple
ExecStart={BIN_PATH} -c {config_path}
Restart=always
RestartSec=3
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
"""
    path = os.path.join(SYSTEMD_DIR, service_name)
    with open(path, "w") as f:
        f.write(content)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", service_name])
    run(["systemctl", "restart", service_name])
    ok(f"Service {service_name} created and started.")
    return service_name


def remove_tunnel_service(service_name):
    run(["systemctl", "stop", service_name])
    run(["systemctl", "disable", service_name])
    path = os.path.join(SYSTEMD_DIR, service_name)
    if os.path.exists(path):
        os.remove(path)
    run(["systemctl", "daemon-reload"])


def create_reset_timer(name, interval_seconds):
    service_name = unique_service_name(name)
    timer_service = unique_timer_service_name(name)
    timer_unit = unique_timer_name(name)

    service_content = f"""[Unit]
Description=Restart timer for {service_name}

[Service]
Type=oneshot
ExecStart=/bin/systemctl restart {service_name}
"""
    timer_content = f"""[Unit]
Description=Periodic restart for {service_name}

[Timer]
OnUnitActiveSec={interval_seconds}s
OnBootSec={interval_seconds}s
Unit={timer_service}

[Install]
WantedBy=timers.target
"""
    with open(os.path.join(SYSTEMD_DIR, timer_service), "w") as f:
        f.write(service_content)
    with open(os.path.join(SYSTEMD_DIR, timer_unit), "w") as f:
        f.write(timer_content)

    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "--now", timer_unit])
    ok(f"Restart timer enabled every {interval_seconds} seconds ({timer_unit}).")
    return timer_unit, timer_service


def remove_reset_timer(name):
    timer_unit = unique_timer_name(name)
    timer_service = unique_timer_service_name(name)
    run(["systemctl", "stop", timer_unit])
    run(["systemctl", "disable", timer_unit])
    for unit in (timer_unit, timer_service):
        p = os.path.join(SYSTEMD_DIR, unit)
        if os.path.exists(p):
            os.remove(p)
    run(["systemctl", "daemon-reload"])


def ask_reset_timer():
    if not prompt_yes_no("Enable automatic restart timer?", default=False):
        return None
    unit = prompt_choice("Time unit:", [("1", "Hours"), ("2", "Minutes")], allow_back=False)
    value = prompt_int("Enter the value", default=1, min_val=1)
    interval = value * 3600 if unit == "1" else value * 60
    return interval


def service_is_active(service_name):
    result = run(["systemctl", "is-active", service_name], capture=True)
    if result is None or not hasattr(result, "stdout"):
        return "unknown"
    status = (result.stdout or "").strip()
    return status or "unknown"


def ask_common_server_fields(transport):
    port = prompt_port("Tunnel port (bind port)", default=8443)
    fields = {
        "bind_addr": f"0.0.0.0:{port}",
        "transport": transport,
        "token": prompt_str("Token (shared between server and client)"),
        "keepalive_period": prompt_int("Keepalive period (seconds)", default=75, min_val=1),
        "nodelay": prompt_yes_no("Enable nodelay?", default=True),
        "channel_size": prompt_int("Channel size", default=2048, min_val=1),
        "heartbeat": prompt_int("Heartbeat interval (seconds)", default=40, min_val=1),
        "log_level": "info",
    }

    if transport in UDP_OVER_TCP_ELIGIBLE:
        fields["accept_udp"] = prompt_yes_no(
            "Enable UDP-over-TCP (forward UDP traffic through this tunnel)?", default=False)

    if prompt_yes_no("Enable sniffer (traffic logging)?", default=False):
        fields["sniffer"] = True
        fields["sniffer_log"] = "/var/log/backhaul-sniffer.json"
    else:
        fields["sniffer"] = False
        fields["sniffer_log"] = ""
    if prompt_yes_no("Enable web interface?", default=False):
        fields["web_port"] = prompt_port("Web interface port", default=2060)
    else:
        fields["web_port"] = 0

    if transport in MUX_TRANSPORTS:
        fields["mux_con"] = prompt_int("Mux concurrency (mux_con)", default=8, min_val=1)
        fields["mux_version"] = prompt_int("Mux version (mux_version)", default=1, min_val=1)
        fields["mux_framesize"] = prompt_int("Mux frame size", default=32768, min_val=1024)
        fields["mux_recievebuffer"] = prompt_int("Mux receive buffer", default=4194304, min_val=1024)
        fields["mux_streambuffer"] = prompt_int("Mux stream buffer", default=65536, min_val=1024)

    if transport in {"tcp", "tcpmux"}:
        if prompt_yes_no("Tune advanced TCP socket options (mss/buffers)?", default=False):
            fields["mss"] = prompt_int("MSS (0 = auto)", default=0, min_val=0)
            fields["so_rcvbuf"] = prompt_int("SO_RCVBUF (0 = system default)", default=0, min_val=0)
            fields["so_sndbuf"] = prompt_int("SO_SNDBUF (0 = system default)", default=0, min_val=0)

    if transport in TLS_TRANSPORTS:
        info("WSS requires a TLS certificate.")
        if prompt_yes_no("Generate a self-signed certificate automatically?", default=True):
            name = f"server-{int(time.time())}"
            crt, key = generate_self_signed_cert(name)
            if crt and key:
                fields["tls_cert"] = crt
                fields["tls_key"] = key
        else:
            fields["tls_cert"] = prompt_str("Path to certificate file (.crt)")
            fields["tls_key"] = prompt_str("Path to private key file (.key)")

    return fields


def ask_common_client_fields(transport):
    remote_ip = prompt_str("Iran server address (IPv4/IPv6)")
    if ":" in remote_ip and not remote_ip.startswith("["):
        remote_ip = f"[{remote_ip}]"
    tunnel_port = prompt_port("Server tunnel port")
    fields = {
        "remote_addr": f"{remote_ip}:{tunnel_port}",
        "transport": transport,
        "token": prompt_str("Token (shared between server and client)"),
        "connection_pool": prompt_int("Connection pool", default=8, min_val=1),
        "aggressive_pool": prompt_yes_no("Enable aggressive pool?", default=False),
        "keepalive_period": prompt_int("Keepalive period (seconds)", default=75, min_val=1),
        "dial_timeout": prompt_int("Dial timeout (seconds)", default=10, min_val=1),
        "nodelay": prompt_yes_no("Enable nodelay?", default=True),
        "retry_interval": prompt_int("Retry interval (seconds)", default=3, min_val=1),
        "log_level": "info",
    }

    if transport in UDP_OVER_TCP_ELIGIBLE:
        fields["accept_udp"] = prompt_yes_no(
            "Enable UDP-over-TCP (forward UDP traffic through this tunnel)?", default=False)

    if transport in WS_TRANSPORTS:
        if prompt_yes_no("Connect through a CDN edge IP (e.g. Cloudflare) instead of connecting directly?",
                          default=False):
            fields["edge_ip"] = prompt_str("Edge IP address")

    if prompt_yes_no("Enable sniffer (traffic logging)?", default=False):
        fields["sniffer"] = True
        fields["sniffer_log"] = "/var/log/backhaul-sniffer.json"
    else:
        fields["sniffer"] = False
        fields["sniffer_log"] = ""
    if prompt_yes_no("Enable web interface?", default=False):
        fields["web_port"] = prompt_port("Web interface port", default=2060)
    else:
        fields["web_port"] = 0

    if transport in MUX_TRANSPORTS:
        fields["mux_version"] = prompt_int("Mux version (mux_version)", default=1, min_val=1)
        fields["mux_framesize"] = prompt_int("Mux frame size", default=32768, min_val=1024)
        fields["mux_recievebuffer"] = prompt_int("Mux receive buffer", default=4194304, min_val=1024)
        fields["mux_streambuffer"] = prompt_int("Mux stream buffer", default=65536, min_val=1024)

    if transport in {"tcp", "tcpmux"}:
        if prompt_yes_no("Tune advanced TCP socket options (mss/buffers)?", default=False):
            fields["mss"] = prompt_int("MSS (0 = auto)", default=0, min_val=0)
            fields["so_rcvbuf"] = prompt_int("SO_RCVBUF (0 = system default)", default=0, min_val=0)
            fields["so_sndbuf"] = prompt_int("SO_SNDBUF (0 = system default)", default=0, min_val=0)

    if transport in TLS_TRANSPORTS:
        fields["tls"] = True

    return fields


def create_tunnel_flow(role):
    banner(f"Create New Tunnel ({'Iran Server' if role == 'server' else 'Kharej Client'})")
    ensure_binary_installed()
    hr()

    while True:
        name = prompt_str("Enter a unique name for this tunnel (letters/numbers/dashes only)")
        if not re.match(r"^[a-zA-Z0-9_-]+$", name):
            warn("Name may only contain letters, numbers, _ and -.")
            continue
        if name_exists(name):
            warn(f"A tunnel named '{name}' already exists. Choose a different name.")
            continue
        break

    transport_options = [(str(i + 1), TRANSPORT_LABELS[t]) for i, t in enumerate(TRANSPORTS)]
    choice = prompt_choice("Select transport type:", transport_options, allow_back=True)
    if choice is None:
        return
    transport = TRANSPORTS[int(choice) - 1]

    hr()
    if role == "server":
        config = ask_common_server_fields(transport)
        if transport != "udp":
            info("Now specify the ports you want to forward:")
            config["ports"] = ask_ports_wizard()
        section = "server"
    else:
        config = ask_common_client_fields(transport)
        section = "client"

    config_path = os.path.join(CONFIG_DIR, f"{name}.toml")
    write_toml(config_path, section, config)
    ok(f"Config file created at {config_path}.")

    service_name = create_tunnel_service(name, config_path)

    hr()
    interval = ask_reset_timer()
    if interval:
        timer_unit, timer_service = create_reset_timer(name, interval)
        timer_info = {"enabled": True, "interval_seconds": interval, "timer_unit": timer_unit}
    else:
        timer_info = {"enabled": False}

    add_tunnel({
        "name": name,
        "role": role,
        "transport": transport,
        "config_path": config_path,
        "service_name": service_name,
        "reset_timer": timer_info,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })

    hr()
    ok(f"Tunnel '{name}' created and started successfully.")
    print(f"{C.WHITE}Service status:{C.RESET} ", end="")
    run(["systemctl", "--no-pager", "status", service_name, "-l", "-n", "5"])
    pause()


def list_tunnels_table():
    tunnels = load_registry()
    if not tunnels:
        warn("No tunnels have been created yet.")
        return []
    print(f"{C.WHITE}{'#':<3}{'Name':<18}{'Role':<10}{'Transport':<12}{'Status':<12}{'Restart Timer'}{C.RESET}")
    hr(width=70)
    for i, t in enumerate(tunnels, 1):
        status = service_is_active(t["service_name"])
        status_color = C.GREEN if status == "active" else (C.RED if status == "failed" else C.YELLOW)
        role_label = "Server" if t["role"] == "server" else "Client"
        timer = t.get("reset_timer") or {}
        timer_txt = f"{timer.get('interval_seconds', 0)}s" if timer.get("enabled") else "-"
        print(f"{i:<3}{t['name']:<18}{role_label:<10}{t['transport']:<12}"
              f"{status_color}{status:<12}{C.RESET}{timer_txt}")
    return tunnels


def show_status_menu():
    banner("Tunnel Status")
    tunnels = list_tunnels_table()
    if not tunnels:
        pause()
        return
    hr()
    if prompt_yes_no("View live logs for one of the services?", default=False):
        idx = prompt_int("Tunnel number", min_val=1, max_val=len(tunnels))
        t = tunnels[idx - 1]
        info("Press Ctrl+C to exit the live log view.")
        try:
            run(["journalctl", "-u", t["service_name"], "-f", "-n", "30"])
        except KeyboardInterrupt:
            pass
    pause()


def edit_tunnel_flow():
    banner("Edit Tunnel")
    tunnels = list_tunnels_table()
    if not tunnels:
        pause()
        return
    hr()
    idx = prompt_int("Tunnel number to edit (0 to go back)", min_val=0, max_val=len(tunnels))
    if idx == 0:
        return
    t = tunnels[idx - 1]

    existing = read_toml_simple(t["config_path"])
    info(f"Editing tunnel '{t['name']}' ({TRANSPORT_LABELS.get(t['transport'], t['transport'])})")
    warn("Current values are shown as defaults; press Enter to keep them unchanged.")
    hr()

    if t["role"] == "server":
        config = ask_common_server_fields_with_defaults(t["transport"], existing)
        if t["transport"] != "udp":
            if prompt_yes_no("Rebuild the list of forwarded ports?", default=False):
                config["ports"] = ask_ports_wizard()
            else:
                config["ports"] = existing.get("ports", [])
        section = "server"
    else:
        config = ask_common_client_fields_with_defaults(t["transport"], existing)
        section = "client"

    write_toml(t["config_path"], section, config)
    ok("Config updated.")
    run(["systemctl", "restart", t["service_name"]])
    ok(f"Service {t['service_name']} restarted.")
    pause()


def ask_common_server_fields_with_defaults(transport, existing):
    default_port = 8443
    if "bind_addr" in existing and ":" in existing["bind_addr"]:
        try:
            default_port = int(existing["bind_addr"].rsplit(":", 1)[1])
        except ValueError:
            pass
    port = prompt_port("Tunnel port (bind port)", default=default_port)
    fields = {
        "bind_addr": f"0.0.0.0:{port}",
        "transport": transport,
        "token": prompt_str("Token", default=existing.get("token", "")),
        "keepalive_period": prompt_int("Keepalive period", default=existing.get("keepalive_period", 75)),
        "nodelay": prompt_yes_no("nodelay?", default=existing.get("nodelay", True)),
        "channel_size": prompt_int("Channel size", default=existing.get("channel_size", 2048)),
        "heartbeat": prompt_int("Heartbeat interval", default=existing.get("heartbeat", 40)),
        "log_level": "info",
    }
    if transport in UDP_OVER_TCP_ELIGIBLE:
        fields["accept_udp"] = prompt_yes_no("UDP-over-TCP?", default=existing.get("accept_udp", False))
    fields["sniffer"] = prompt_yes_no("sniffer?", default=existing.get("sniffer", False))
    fields["sniffer_log"] = "/var/log/backhaul-sniffer.json" if fields["sniffer"] else ""
    if prompt_yes_no("Web UI?", default=bool(existing.get("web_port", 0))):
        fields["web_port"] = prompt_port("Web interface port", default=existing.get("web_port") or 2060)
    else:
        fields["web_port"] = 0
    if transport in MUX_TRANSPORTS:
        fields["mux_con"] = prompt_int("mux_con", default=existing.get("mux_con", 8))
        fields["mux_version"] = prompt_int("mux_version", default=existing.get("mux_version", 1))
        fields["mux_framesize"] = prompt_int("mux_framesize", default=existing.get("mux_framesize", 32768))
        fields["mux_recievebuffer"] = prompt_int("mux_recievebuffer", default=existing.get("mux_recievebuffer", 4194304))
        fields["mux_streambuffer"] = prompt_int("mux_streambuffer", default=existing.get("mux_streambuffer", 65536))
    if transport in {"tcp", "tcpmux"} and ("mss" in existing or prompt_yes_no("Tune advanced TCP socket options?", default=False)):
        fields["mss"] = prompt_int("MSS (0 = auto)", default=existing.get("mss", 0), min_val=0)
        fields["so_rcvbuf"] = prompt_int("SO_RCVBUF (0 = default)", default=existing.get("so_rcvbuf", 0), min_val=0)
        fields["so_sndbuf"] = prompt_int("SO_SNDBUF (0 = default)", default=existing.get("so_sndbuf", 0), min_val=0)
    if transport in TLS_TRANSPORTS:
        fields["tls_cert"] = prompt_str("Path to certificate (.crt)", default=existing.get("tls_cert", ""))
        fields["tls_key"] = prompt_str("Path to key (.key)", default=existing.get("tls_key", ""))
    return fields


def ask_common_client_fields_with_defaults(transport, existing):
    default_remote = existing.get("remote_addr", "")
    default_ip, default_port = "", 443
    if ":" in default_remote:
        default_ip, _, p = default_remote.rpartition(":")
        try:
            default_port = int(p)
        except ValueError:
            pass
    remote_ip = prompt_str("Iran server address (IPv4/IPv6)", default=default_ip.strip("[]") or None)
    if ":" in remote_ip and not remote_ip.startswith("["):
        remote_ip = f"[{remote_ip}]"
    tunnel_port = prompt_port("Server tunnel port", default=default_port)
    fields = {
        "remote_addr": f"{remote_ip}:{tunnel_port}",
        "transport": transport,
        "token": prompt_str("Token", default=existing.get("token", "")),
        "connection_pool": prompt_int("Connection pool", default=existing.get("connection_pool", 8)),
        "aggressive_pool": prompt_yes_no("aggressive pool?", default=existing.get("aggressive_pool", False)),
        "keepalive_period": prompt_int("Keepalive period", default=existing.get("keepalive_period", 75)),
        "dial_timeout": prompt_int("Dial timeout", default=existing.get("dial_timeout", 10)),
        "nodelay": prompt_yes_no("nodelay?", default=existing.get("nodelay", True)),
        "retry_interval": prompt_int("Retry interval", default=existing.get("retry_interval", 3)),
        "log_level": "info",
    }
    if transport in UDP_OVER_TCP_ELIGIBLE:
        fields["accept_udp"] = prompt_yes_no("UDP-over-TCP?", default=existing.get("accept_udp", False))
    if transport in WS_TRANSPORTS and ("edge_ip" in existing or prompt_yes_no("Use a CDN edge IP?", default=False)):
        fields["edge_ip"] = prompt_str("Edge IP address", default=existing.get("edge_ip", ""))
    fields["sniffer"] = prompt_yes_no("sniffer?", default=existing.get("sniffer", False))
    fields["sniffer_log"] = "/var/log/backhaul-sniffer.json" if fields["sniffer"] else ""
    if prompt_yes_no("Web UI?", default=bool(existing.get("web_port", 0))):
        fields["web_port"] = prompt_port("Web interface port", default=existing.get("web_port") or 2060)
    else:
        fields["web_port"] = 0
    if transport in MUX_TRANSPORTS:
        fields["mux_version"] = prompt_int("mux_version", default=existing.get("mux_version", 1))
        fields["mux_framesize"] = prompt_int("mux_framesize", default=existing.get("mux_framesize", 32768))
        fields["mux_recievebuffer"] = prompt_int("mux_recievebuffer", default=existing.get("mux_recievebuffer", 4194304))
        fields["mux_streambuffer"] = prompt_int("mux_streambuffer", default=existing.get("mux_streambuffer", 65536))
    if transport in {"tcp", "tcpmux"} and ("mss" in existing or prompt_yes_no("Tune advanced TCP socket options?", default=False)):
        fields["mss"] = prompt_int("MSS (0 = auto)", default=existing.get("mss", 0), min_val=0)
        fields["so_rcvbuf"] = prompt_int("SO_RCVBUF (0 = default)", default=existing.get("so_rcvbuf", 0), min_val=0)
        fields["so_sndbuf"] = prompt_int("SO_SNDBUF (0 = default)", default=existing.get("so_sndbuf", 0), min_val=0)
    if transport in TLS_TRANSPORTS:
        fields["tls"] = True
    return fields


def uninstall_flow():
    banner("Remove Tunnel")
    tunnels = list_tunnels_table()
    if not tunnels:
        pause()
        return
    hr()
    info("You can enter several numbers separated by commas (e.g. 1,3,4) or 'all' to remove everything.")
    raw = prompt_str("Tunnel number(s) to remove (0 to go back)")
    if raw.strip() == "0":
        return

    if raw.strip().lower() == "all":
        targets = tunnels
    else:
        indices = []
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit() and 1 <= int(part) <= len(tunnels):
                indices.append(int(part))
            else:
                warn(f"Ignored invalid value: {part}")
        targets = [tunnels[i - 1] for i in indices]

    if not targets:
        warn("No valid tunnels were selected.")
        pause()
        return

    print(f"{C.RED}The following will be permanently removed:{C.RESET}")
    for t in targets:
        print(f"  - {t['name']} ({t['role']}, {t['transport']})")

    if not prompt_yes_no("Are you sure? This cannot be undone.", default=False):
        warn("Operation cancelled.")
        pause()
        return

    for t in targets:
        remove_tunnel_service(t["service_name"])
        timer = t.get("reset_timer") or {}
        if timer.get("enabled"):
            remove_reset_timer(t["name"])
        if os.path.exists(t["config_path"]):
            os.remove(t["config_path"])
        remove_tunnel_entry(t["name"])
        ok(f"Tunnel '{t['name']}' removed.")

    pause()


def monitor_flow():
    banner("Traffic Monitoring (TCPdump)")
    tunnels = list_tunnels_table()
    if not tunnels:
        pause()
        return
    hr()
    idx = prompt_int("Tunnel number (0 to go back)", min_val=0, max_val=len(tunnels))
    if idx == 0:
        return
    t = tunnels[idx - 1]
    cfg = read_toml_simple(t["config_path"])
    ports = set()
    if "bind_addr" in cfg:
        try:
            ports.add(int(cfg["bind_addr"].rsplit(":", 1)[1]))
        except ValueError:
            pass
    if "remote_addr" in cfg:
        try:
            ports.add(int(cfg["remote_addr"].rsplit(":", 1)[1]))
        except ValueError:
            pass
    for p in cfg.get("ports", []):
        for token in re.split("[:=]", p):
            token = token.strip()
            if token.isdigit():
                ports.add(int(token))

    if not ports:
        warn("No ports found for this tunnel.")
        pause()
        return

    duration = prompt_int("Monitoring duration (seconds)", default=10, min_val=1, max_val=300)
    port_filter = " or ".join(f"port {p}" for p in ports)
    info(f"Monitoring ports {sorted(ports)} for {duration} seconds...")
    result = run(f"timeout {duration} tcpdump -i any -n -q {port_filter}", capture=True)
    if result and hasattr(result, "stdout"):
        lines = (result.stdout or "").strip().splitlines()
        print(f"{C.WHITE}Packets observed: {len(lines)}{C.RESET}")
    pause()


def create_menu():
    banner("Create New Tunnel")
    choice = prompt_choice("Select this server's role:", [
        ("1", "Iran Server"),
        ("2", "Kharej Client"),
    ])
    if choice is None:
        return
    role = "server" if choice == "1" else "client"
    create_tunnel_flow(role)


def update_binary_menu():
    banner("Update Backhaul Binary")
    download_binary(force_update=True)
    pause()


def main_menu():
    ensure_dirs()
    while True:
        banner("Main Menu")
        hr()
        options = [
            ("1", "Create new tunnel"),
            ("2", "Tunnel status"),
            ("3", "Edit tunnel"),
            ("4", "Remove tunnel"),
            ("5", "Traffic monitoring (TCPdump)"),
            ("6", "Check/update Backhaul binary"),
        ]
        for key, desc in options:
            print(f"  {C.GREEN}{key}{C.RESET})  {desc}")
        print(f"  {C.RED}0{C.RESET})  Exit")
        hr()
        try:
            choice = input(f"{C.PINK}Your choice: {C.RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            ok("Goodbye!")
            break

        if choice == "1":
            create_menu()
        elif choice == "2":
            show_status_menu()
        elif choice == "3":
            edit_tunnel_flow()
        elif choice == "4":
            uninstall_flow()
        elif choice == "5":
            monitor_flow()
        elif choice == "6":
            update_binary_menu()
        elif choice == "0":
            ok("Goodbye!")
            break
        else:
            warn("Invalid option.")
            pause()


def main():
    require_root()
    try:
        main_menu()
    except KeyboardInterrupt:
        print()
        ok("Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
