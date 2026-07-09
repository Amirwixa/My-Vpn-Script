#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backhaul Manager (bhmgr) - نسخه بازنویسی‌شده
مدیریت تانل‌های Backhaul (سرور ایران / کلاینت خارج) با پشتیبانی از تعداد نامحدود
تانل هم‌زمان، بدون بازنویسی تصادفی کانفیگ‌ها.

نسخه اصلی: https://github.com/Azumi67/Backhaul_script
این نسخه با هدف رفع باگ‌ها و ساده‌تر کردن کار با اسکریپت بازنویسی شده.
"""

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

# ----------------------------------------------------------------------------
# مسیرها و ثابت‌ها
# ----------------------------------------------------------------------------

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


# ----------------------------------------------------------------------------
# رنگ‌ها و چاپ
# ----------------------------------------------------------------------------

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
    print(f"{C.RED}✘ خطا: {msg}{C.RESET}")


def warn(msg):
    print(f"{C.YELLOW}⚠ {msg}{C.RESET}")


def info(msg):
    print(f"{C.CYAN}ℹ {msg}{C.RESET}")


def pause():
    try:
        input(f"\n{C.GRAY}برای ادامه Enter را بزنید...{C.RESET}")
    except (KeyboardInterrupt, EOFError):
        pass


# ----------------------------------------------------------------------------
# ورودی امن (validation + عدم کرش)
# ----------------------------------------------------------------------------

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
            warn("این فیلد نمی‌تواند خالی باشد.")
            continue
        return raw


def prompt_int(label, default=None, min_val=None, max_val=None):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{C.YELLOW}{label}{suffix}: {C.RESET}").strip()
        if not raw and default is not None:
            return default
        if not raw.lstrip("-").isdigit():
            warn("لطفاً یک عدد معتبر وارد کنید.")
            continue
        val = int(raw)
        if min_val is not None and val < min_val:
            warn(f"عدد باید حداقل {min_val} باشد.")
            continue
        if max_val is not None and val > max_val:
            warn(f"عدد باید حداکثر {max_val} باشد.")
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
        if raw in ("y", "yes", "بله", "آره"):
            return True
        if raw in ("n", "no", "خیر", "نه"):
            return False
        warn("لطفاً y یا n وارد کنید.")


def prompt_choice(label, options, allow_back=True):
    """options: list of (key, description). Returns chosen key, or None for back."""
    while True:
        print(f"{C.YELLOW}╭{'─' * 44}╮{C.RESET}")
        print(f"{C.YELLOW}{label}{C.RESET}")
        for key, desc in options:
            print(f"  {C.GREEN}{key}{C.RESET})  {desc}")
        if allow_back:
            print(f"  {C.BLUE}0{C.RESET})  بازگشت")
        print(f"{C.YELLOW}╰{'─' * 44}╯{C.RESET}")
        raw = input(f"{C.PINK}انتخاب شما: {C.RESET}").strip()
        if allow_back and raw == "0":
            return None
        valid_keys = [str(k) for k, _ in options]
        if raw in valid_keys:
            for k, _ in options:
                if str(k) == raw:
                    return k
        warn("گزینه نامعتبر است، دوباره تلاش کنید.")


def require_root():
    if os.geteuid() != 0:
        err("این برنامه باید با دسترسی root اجرا شود. لطفاً با sudo اجرا کنید:")
        print(f"{C.WHITE}sudo bhmgr{C.RESET}")
        sys.exit(1)


def run(cmd, check=False, capture=False):
    """اجرای امن یک دستور شل، بدون کرش کردن کل برنامه در صورت خطا."""
    try:
        result = subprocess.run(
            cmd, shell=isinstance(cmd, str), check=check,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            text=True,
        )
        return result
    except subprocess.CalledProcessError as e:
        err(f"دستور با خطا مواجه شد: {cmd}\n{e}")
        return e
    except FileNotFoundError:
        err(f"دستور پیدا نشد: {cmd}")
        return None


# ----------------------------------------------------------------------------
# رجیستری تانل‌ها (به‌جای ۱۰ اسلات هاردکد، تعداد نامحدود با نام دلخواه)
# ----------------------------------------------------------------------------

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
        warn("فایل رجیستری خراب بود، یک رجیستری جدید ساخته می‌شود.")
        backup = REGISTRY_FILE + f".broken.{int(time.time())}"
        try:
            shutil.copy(REGISTRY_FILE, backup)
            warn(f"نسخه خراب در {backup} نگه داشته شد.")
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


# ----------------------------------------------------------------------------
# نصب پیش‌نیازها و دانلود باینری (نسخه‌ی همیشه به‌روز، نه هاردکد)
# ----------------------------------------------------------------------------

def install_prerequisites():
    system = platform.system()
    if system == "Linux":
        info("در حال به‌روزرسانی لیست پکیج‌ها...")
        run(["apt-get", "update", "-y"])
        info("در حال نصب wget, curl, tar, openssl, tcpdump...")
        run(["apt-get", "install", "-y", "wget", "curl", "tar", "openssl", "tcpdump"])
    elif system == "Darwin":
        run(["brew", "install", "wget", "curl", "gnu-tar", "openssl"])
    else:
        err("این سیستم‌عامل پشتیبانی نمی‌شود.")
        sys.exit(1)


def get_latest_version():
    """آخرین نسخه‌ی منتشرشده‌ی Backhaul را از GitHub می‌گیرد. در صورت شکست، نسخه‌ی fallback را برمی‌گرداند."""
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
    warn(f"دریافت آخرین نسخه ممکن نشد، از نسخه‌ی {FALLBACK_VERSION} استفاده می‌شود.")
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
        err(f"سیستم‌عامل/معماری پشتیبانی نمی‌شود: {os_name}/{arch}")
        sys.exit(1)

    target_version = get_latest_version()
    current_version = installed_version()

    if os.path.exists(BIN_PATH) and current_version == target_version and not force_update:
        ok(f"باینری Backhaul نسخه {current_version} از قبل نصب است.")
        return

    if os.path.exists(BIN_PATH) and current_version and current_version != target_version:
        info(f"نسخه فعلی: {current_version} → نسخه جدید موجود: {target_version}")
        if not prompt_yes_no("آیا می‌خواهید باینری آپدیت شود؟", default=True):
            return

    asset = f"backhaul_{os_name}_{mapped_arch}.tar.gz"
    url = f"https://github.com/{GITHUB_REPO}/releases/download/{target_version}/{asset}"
    tmp_file = f"/tmp/{asset}"

    info(f"در حال دانلود {asset} (نسخه {target_version})...")
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
        err(f"دانلود ناموفق بود: {e}")
        sys.exit(1)

    info("در حال استخراج باینری...")
    shutil.unpack_archive(tmp_file, BIN_DIR)
    os.chmod(BIN_PATH, 0o755)
    with open(VERSION_FILE, "w") as f:
        f.write(target_version)
    os.remove(tmp_file)
    ok(f"باینری Backhaul نسخه {target_version} با موفقیت نصب شد.")


def ensure_binary_installed():
    if not os.path.exists(BIN_PATH):
        install_prerequisites()
        download_binary()
    else:
        ok("باینری Backhaul از قبل نصب است.")


# ----------------------------------------------------------------------------
# TOML نویسی
# ----------------------------------------------------------------------------

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
    """پارس ساده‌ی فایل toml تولیدشده توسط خودمان (برای ویرایش)."""
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


# ----------------------------------------------------------------------------
# ویزارد پورت فوروارد (سمت سرور)
# ----------------------------------------------------------------------------

def ask_ports_wizard():
    ports = []
    mode = prompt_choice("نوع Forward را انتخاب کنید:", [
        ("1", "فوروارد پورت معمولی"),
        ("2", "فوروارد بازه‌ی پورت (Range)"),
    ], allow_back=False)

    if mode == "1":
        sub = prompt_choice("نوع فوروارد پورت:", [
            ("1", "فوروارد ساده (local = remote)"),
            ("2", "از یک IP محلی مشخص"),
            ("3", "به یک IP ریموت مشخص"),
            ("4", "از IP محلی مشخص به IP ریموت مشخص"),
        ], allow_back=False)

        count = prompt_int("چند پورت می‌خواهید فوروارد کنید؟", default=1, min_val=1, max_val=200)
        for i in range(1, count + 1):
            if sub == "1":
                local_port = prompt_port(f"پورت محلی #{i}")
                remote_port = prompt_port(f"پورت ریموت #{i}", default=local_port)
                ports.append(f"{local_port}={remote_port}")
            elif sub == "2":
                local_ip = prompt_str(f"IP محلی #{i}")
                local_port = prompt_port(f"پورت محلی #{i}")
                remote_port = prompt_port(f"پورت ریموت #{i}", default=local_port)
                ports.append(f"{local_ip}:{local_port}={remote_port}")
            elif sub == "3":
                local_port = prompt_port(f"پورت محلی #{i}")
                remote_ip = prompt_str(f"IP ریموت #{i}")
                remote_port = prompt_port(f"پورت ریموت #{i}", default=local_port)
                ports.append(f"{local_port}={remote_ip}:{remote_port}")
            else:
                local_ip = prompt_str(f"IP محلی #{i}")
                local_port = prompt_port(f"پورت محلی #{i}")
                remote_ip = prompt_str(f"IP ریموت #{i}")
                remote_port = prompt_port(f"پورت ریموت #{i}", default=local_port)
                ports.append(f"{local_ip}:{local_port}={remote_ip}:{remote_port}")
    else:
        sub = prompt_choice("نوع فوروارد بازه‌ی پورت:", [
            ("1", "گوش دادن روی تمام پورت‌های بازه"),
            ("2", "فوروارد به یک پورت مشخص"),
            ("3", "فوروارد به یک IP و پورت مشخص"),
        ], allow_back=False)
        port_range = prompt_str("بازه‌ی پورت را وارد کنید (مثال: 100-900)")
        if not re.match(r"^\d+-\d+$", port_range):
            warn("فرمت بازه نامعتبر بود، به همان شکل ذخیره می‌شود ولی لطفاً بررسی کنید.")
        if sub == "1":
            ports.append(port_range)
        elif sub == "2":
            remote_port = prompt_port("پورت ریموت")
            ports.append(f"{port_range}:{remote_port}")
        else:
            remote_ip = prompt_str("IP ریموت")
            remote_port = prompt_port("پورت ریموت")
            ports.append(f"{port_range}={remote_ip}:{remote_port}")

    return ports


# ----------------------------------------------------------------------------
# گواهی self-signed برای WSS
# ----------------------------------------------------------------------------

def generate_self_signed_cert(cert_name):
    os.makedirs(CERT_DIR, exist_ok=True)
    key_file = os.path.join(CERT_DIR, f"{cert_name}.key")
    csr_file = os.path.join(CERT_DIR, f"{cert_name}.csr")
    crt_file = os.path.join(CERT_DIR, f"{cert_name}.crt")

    if run(["which", "openssl"], capture=True).returncode != 0:
        err("openssl نصب نیست. با دستور زیر نصبش کنید: apt-get install -y openssl")
        return None, None

    run(["openssl", "genpkey", "-algorithm", "RSA", "-out", key_file,
         "-pkeyopt", "rsa_keygen_bits:2048"], check=True)
    run(["openssl", "req", "-new", "-key", key_file, "-out", csr_file,
         "-subj", f"/C=US/ST=NA/L=NA/O=Backhaul/CN={cert_name}"], check=True)
    run(["openssl", "x509", "-req", "-in", csr_file, "-signkey", key_file,
         "-out", crt_file, "-days", "825"], check=True)
    ok(f"گواهی ساخته شد: {crt_file}")
    return crt_file, key_file


# ----------------------------------------------------------------------------
# systemd: سرویس اصلی تانل و تایمر ری‌استارت
# ----------------------------------------------------------------------------

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
    ok(f"سرویس {service_name} ساخته و اجرا شد.")
    return service_name


def remove_tunnel_service(service_name):
    run(["systemctl", "stop", service_name])
    run(["systemctl", "disable", service_name])
    path = os.path.join(SYSTEMD_DIR, service_name)
    if os.path.exists(path):
        os.remove(path)
    run(["systemctl", "daemon-reload"])


def create_reset_timer(name, interval_seconds):
    """به‌جای اسکریپت bash با while true (که در نسخه‌ی اصلی بود)، از systemd timer
    استفاده می‌کنیم که استانداردتر، سبک‌تر و قابل مانیتور کردن با systemctl است."""
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
    ok(f"تایمر ری‌استارت هر {interval_seconds} ثانیه فعال شد ({timer_unit}).")
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
    if not prompt_yes_no("می‌خواهید تایمر ری‌استارت خودکار فعال شود؟", default=False):
        return None
    unit = prompt_choice("واحد زمانی:", [("1", "ساعت"), ("2", "دقیقه")], allow_back=False)
    value = prompt_int("عدد مورد نظر را وارد کنید", default=1, min_val=1)
    interval = value * 3600 if unit == "1" else value * 60
    return interval


def service_is_active(service_name):
    result = run(["systemctl", "is-active", service_name], capture=True)
    if result is None or not hasattr(result, "stdout"):
        return "نامشخص"
    status = (result.stdout or "").strip()
    return status or "نامشخص"


# ----------------------------------------------------------------------------
# جمع‌آوری تنظیمات سرور / کلاینت برای هر transport (به‌جای ۱۴ تابع تکراری،
# یک تابع پارامتری)
# ----------------------------------------------------------------------------

def ask_common_server_fields(transport):
    port = prompt_port("پورت تانل (Bind Port)", default=8443)
    fields = {
        "bind_addr": f"0.0.0.0:{port}",
        "transport": transport,
        "token": prompt_str("توکن (Token) مشترک بین سرور و کلاینت"),
        "keepalive_period": prompt_int("Keepalive period (ثانیه)", default=75, min_val=1),
        "nodelay": prompt_yes_no("فعال‌سازی nodelay؟", default=True),
        "channel_size": prompt_int("Channel size", default=2048, min_val=1),
        "heartbeat": prompt_int("Heartbeat interval (ثانیه)", default=40, min_val=1),
        "log_level": "info",
    }
    if transport == "udp":
        pass
    if prompt_yes_no("فعال‌سازی sniffer (لاگ ترافیک)؟", default=False):
        fields["sniffer"] = True
        fields["sniffer_log"] = "/var/log/backhaul-sniffer.json"
    else:
        fields["sniffer"] = False
        fields["sniffer_log"] = ""
    if prompt_yes_no("فعال‌سازی وب‌اینترفیس (Web UI)؟", default=False):
        fields["web_port"] = prompt_port("پورت وب‌اینترفیس", default=2060)
    else:
        fields["web_port"] = 0

    if transport in MUX_TRANSPORTS:
        fields["mux_con"] = prompt_int("تعداد کانکشن Mux (mux_con)", default=8, min_val=1)
        fields["mux_version"] = prompt_int("نسخه‌ی Mux (mux_version)", default=1, min_val=1)
        fields["mux_framesize"] = prompt_int("Mux frame size", default=32768, min_val=1024)
        fields["mux_recievebuffer"] = prompt_int("Mux receive buffer", default=4194304, min_val=1024)
        fields["mux_streambuffer"] = prompt_int("Mux stream buffer", default=65536, min_val=1024)

    if transport in TLS_TRANSPORTS:
        info("برای WSS به گواهی TLS نیاز است.")
        if prompt_yes_no("گواهی self-signed خودکار ساخته شود؟", default=True):
            name = f"server-{int(time.time())}"
            crt, key = generate_self_signed_cert(name)
            if crt and key:
                fields["tls_cert"] = crt
                fields["tls_key"] = key
        else:
            fields["tls_cert"] = prompt_str("مسیر فایل گواهی (.crt)")
            fields["tls_key"] = prompt_str("مسیر فایل کلید خصوصی (.key)")

    return fields


def ask_common_client_fields(transport):
    remote_ip = prompt_str("آدرس سرور ایران (IPv4/IPv6)")
    if ":" in remote_ip and not remote_ip.startswith("["):
        remote_ip = f"[{remote_ip}]"
    tunnel_port = prompt_port("پورت تانل سرور")
    fields = {
        "remote_addr": f"{remote_ip}:{tunnel_port}",
        "transport": transport,
        "token": prompt_str("توکن (Token) مشترک بین سرور و کلاینت"),
        "connection_pool": prompt_int("Connection pool", default=8, min_val=1),
        "aggressive_pool": prompt_yes_no("فعال‌سازی aggressive pool؟", default=False),
        "keepalive_period": prompt_int("Keepalive period (ثانیه)", default=75, min_val=1),
        "dial_timeout": prompt_int("Dial timeout (ثانیه)", default=10, min_val=1),
        "nodelay": prompt_yes_no("فعال‌سازی nodelay؟", default=True),
        "retry_interval": prompt_int("Retry interval (ثانیه)", default=3, min_val=1),
        "log_level": "info",
    }
    if prompt_yes_no("فعال‌سازی sniffer (لاگ ترافیک)؟", default=False):
        fields["sniffer"] = True
        fields["sniffer_log"] = "/var/log/backhaul-sniffer.json"
    else:
        fields["sniffer"] = False
        fields["sniffer_log"] = ""
    if prompt_yes_no("فعال‌سازی وب‌اینترفیس (Web UI)؟", default=False):
        fields["web_port"] = prompt_port("پورت وب‌اینترفیس", default=2060)
    else:
        fields["web_port"] = 0

    if transport in MUX_TRANSPORTS:
        fields["mux_version"] = prompt_int("نسخه‌ی Mux (mux_version)", default=1, min_val=1)
        fields["mux_framesize"] = prompt_int("Mux frame size", default=32768, min_val=1024)
        fields["mux_recievebuffer"] = prompt_int("Mux receive buffer", default=4194304, min_val=1024)
        fields["mux_streambuffer"] = prompt_int("Mux stream buffer", default=65536, min_val=1024)

    if transport in TLS_TRANSPORTS:
        fields["tls"] = True  # اطلاعات لازم برای اتصال به سرور WSS، سمت کلاینت گواهی جدا نمی‌خواهد.

    return fields


def create_tunnel_flow(role):
    """جریان کامل ساخت تانل: نام یکتا -> transport -> تنظیمات -> کانفیگ -> سرویس -> تایمر."""
    banner(f"ساخت تانل جدید ({'سرور ایران' if role == 'server' else 'کلاینت خارج'})")
    ensure_binary_installed()
    hr()

    while True:
        name = prompt_str("یک نام یکتا برای این تانل انتخاب کنید (فقط حروف/عدد/خط تیره)")
        if not re.match(r"^[a-zA-Z0-9_-]+$", name):
            warn("نام فقط می‌تواند شامل حروف انگلیسی، عدد، _ و - باشد.")
            continue
        if name_exists(name):
            warn(f"تانلی با نام «{name}» از قبل وجود دارد. یک نام دیگر انتخاب کنید.")
            continue
        break

    transport_options = [(str(i + 1), TRANSPORT_LABELS[t]) for i, t in enumerate(TRANSPORTS)]
    choice = prompt_choice("نوع Transport را انتخاب کنید:", transport_options, allow_back=True)
    if choice is None:
        return
    transport = TRANSPORTS[int(choice) - 1]

    hr()
    if role == "server":
        config = ask_common_server_fields(transport)
        if transport != "udp":
            info("حالا پورت‌هایی که می‌خواهید فوروارد شوند را مشخص کنید:")
            config["ports"] = ask_ports_wizard()
        section = "server"
    else:
        config = ask_common_client_fields(transport)
        section = "client"

    config_path = os.path.join(CONFIG_DIR, f"{name}.toml")
    write_toml(config_path, section, config)
    ok(f"فایل کانفیگ در {config_path} ساخته شد.")

    service_name = create_tunnel_service(name, config_path)

    hr()
    interval = ask_reset_timer()
    timer_info = None
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
    ok(f"تانل «{name}» با موفقیت ساخته و فعال شد.")
    print(f"{C.WHITE}وضعیت سرویس: {C.RESET}", end="")
    run(["systemctl", "--no-pager", "status", service_name, "-l", "-n", "5"])
    pause()


# ----------------------------------------------------------------------------
# لیست / وضعیت تانل‌ها
# ----------------------------------------------------------------------------

def list_tunnels_table():
    tunnels = load_registry()
    if not tunnels:
        warn("هنوز هیچ تانلی ساخته نشده است.")
        return []
    print(f"{C.WHITE}{'#':<3}{'نام':<18}{'نقش':<10}{'نوع':<10}{'وضعیت':<12}{'تایمر ری‌استارت'}{C.RESET}")
    hr(width=70)
    for i, t in enumerate(tunnels, 1):
        status = service_is_active(t["service_name"])
        status_color = C.GREEN if status == "active" else (C.RED if status == "failed" else C.YELLOW)
        role_fa = "سرور" if t["role"] == "server" else "کلاینت"
        timer = t.get("reset_timer") or {}
        timer_txt = f"{timer.get('interval_seconds', 0)}s" if timer.get("enabled") else "-"
        print(f"{i:<3}{t['name']:<18}{role_fa:<10}{t['transport']:<10}"
              f"{status_color}{status:<12}{C.RESET}{timer_txt}")
    return tunnels


def show_status_menu():
    banner("وضعیت تانل‌ها")
    tunnels = list_tunnels_table()
    if not tunnels:
        pause()
        return
    hr()
    if prompt_yes_no("می‌خواهید لاگ زنده‌ی یکی از سرویس‌ها را ببینید؟", default=False):
        idx = prompt_int("شماره‌ی تانل", min_val=1, max_val=len(tunnels))
        t = tunnels[idx - 1]
        info("برای خروج از لاگ زنده Ctrl+C را بزنید.")
        try:
            run(["journalctl", "-u", t["service_name"], "-f", "-n", "30"])
        except KeyboardInterrupt:
            pass
    pause()


# ----------------------------------------------------------------------------
# ویرایش تانل موجود
# ----------------------------------------------------------------------------

def edit_tunnel_flow():
    banner("ویرایش تانل")
    tunnels = list_tunnels_table()
    if not tunnels:
        pause()
        return
    hr()
    idx = prompt_int("شماره‌ی تانلی که می‌خواهید ویرایش کنید (۰ برای بازگشت)", min_val=0, max_val=len(tunnels))
    if idx == 0:
        return
    t = tunnels[idx - 1]

    existing = read_toml_simple(t["config_path"])
    info(f"در حال ویرایش تانل «{t['name']}» ({TRANSPORT_LABELS.get(t['transport'], t['transport'])})")
    warn("مقادیر فعلی به‌عنوان پیش‌فرض نمایش داده می‌شوند؛ فقط Enter بزنید تا همان مقدار حفظ شود.")
    hr()

    if t["role"] == "server":
        config = ask_common_server_fields_with_defaults(t["transport"], existing)
        if t["transport"] != "udp":
            if prompt_yes_no("می‌خواهید لیست پورت‌های فوروارد را دوباره بسازید؟", default=False):
                config["ports"] = ask_ports_wizard()
            else:
                config["ports"] = existing.get("ports", [])
        section = "server"
    else:
        config = ask_common_client_fields_with_defaults(t["transport"], existing)
        section = "client"

    write_toml(t["config_path"], section, config)
    ok("کانفیگ به‌روزرسانی شد.")
    run(["systemctl", "restart", t["service_name"]])
    ok(f"سرویس {t['service_name']} ری‌استارت شد.")
    pause()


def ask_common_server_fields_with_defaults(transport, existing):
    # مقدار پورت فعلی را از bind_addr استخراج می‌کنیم
    default_port = 8443
    if "bind_addr" in existing and ":" in existing["bind_addr"]:
        try:
            default_port = int(existing["bind_addr"].rsplit(":", 1)[1])
        except ValueError:
            pass
    port = prompt_port("پورت تانل (Bind Port)", default=default_port)
    fields = {
        "bind_addr": f"0.0.0.0:{port}",
        "transport": transport,
        "token": prompt_str("توکن (Token)", default=existing.get("token", "")),
        "keepalive_period": prompt_int("Keepalive period", default=existing.get("keepalive_period", 75)),
        "nodelay": prompt_yes_no("nodelay؟", default=existing.get("nodelay", True)),
        "channel_size": prompt_int("Channel size", default=existing.get("channel_size", 2048)),
        "heartbeat": prompt_int("Heartbeat interval", default=existing.get("heartbeat", 40)),
        "log_level": "info",
    }
    fields["sniffer"] = prompt_yes_no("sniffer؟", default=existing.get("sniffer", False))
    fields["sniffer_log"] = "/var/log/backhaul-sniffer.json" if fields["sniffer"] else ""
    if prompt_yes_no("Web UI؟", default=bool(existing.get("web_port", 0))):
        fields["web_port"] = prompt_port("پورت وب‌اینترفیس", default=existing.get("web_port") or 2060)
    else:
        fields["web_port"] = 0
    if transport in MUX_TRANSPORTS:
        fields["mux_con"] = prompt_int("mux_con", default=existing.get("mux_con", 8))
        fields["mux_version"] = prompt_int("mux_version", default=existing.get("mux_version", 1))
        fields["mux_framesize"] = prompt_int("mux_framesize", default=existing.get("mux_framesize", 32768))
        fields["mux_recievebuffer"] = prompt_int("mux_recievebuffer", default=existing.get("mux_recievebuffer", 4194304))
        fields["mux_streambuffer"] = prompt_int("mux_streambuffer", default=existing.get("mux_streambuffer", 65536))
    if transport in TLS_TRANSPORTS:
        fields["tls_cert"] = prompt_str("مسیر گواهی (.crt)", default=existing.get("tls_cert", ""))
        fields["tls_key"] = prompt_str("مسیر کلید (.key)", default=existing.get("tls_key", ""))
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
    remote_ip = prompt_str("آدرس سرور ایران (IPv4/IPv6)", default=default_ip.strip("[]") or None)
    if ":" in remote_ip and not remote_ip.startswith("["):
        remote_ip = f"[{remote_ip}]"
    tunnel_port = prompt_port("پورت تانل سرور", default=default_port)
    fields = {
        "remote_addr": f"{remote_ip}:{tunnel_port}",
        "transport": transport,
        "token": prompt_str("توکن (Token)", default=existing.get("token", "")),
        "connection_pool": prompt_int("Connection pool", default=existing.get("connection_pool", 8)),
        "aggressive_pool": prompt_yes_no("aggressive pool؟", default=existing.get("aggressive_pool", False)),
        "keepalive_period": prompt_int("Keepalive period", default=existing.get("keepalive_period", 75)),
        "dial_timeout": prompt_int("Dial timeout", default=existing.get("dial_timeout", 10)),
        "nodelay": prompt_yes_no("nodelay؟", default=existing.get("nodelay", True)),
        "retry_interval": prompt_int("Retry interval", default=existing.get("retry_interval", 3)),
        "log_level": "info",
    }
    fields["sniffer"] = prompt_yes_no("sniffer؟", default=existing.get("sniffer", False))
    fields["sniffer_log"] = "/var/log/backhaul-sniffer.json" if fields["sniffer"] else ""
    if prompt_yes_no("Web UI؟", default=bool(existing.get("web_port", 0))):
        fields["web_port"] = prompt_port("پورت وب‌اینترفیس", default=existing.get("web_port") or 2060)
    else:
        fields["web_port"] = 0
    if transport in MUX_TRANSPORTS:
        fields["mux_version"] = prompt_int("mux_version", default=existing.get("mux_version", 1))
        fields["mux_framesize"] = prompt_int("mux_framesize", default=existing.get("mux_framesize", 32768))
        fields["mux_recievebuffer"] = prompt_int("mux_recievebuffer", default=existing.get("mux_recievebuffer", 4194304))
        fields["mux_streambuffer"] = prompt_int("mux_streambuffer", default=existing.get("mux_streambuffer", 65536))
    if transport in TLS_TRANSPORTS:
        fields["tls"] = True
    return fields


# ----------------------------------------------------------------------------
# حذف تانل (به‌جای ۲۰ تابع uninstall_multi_iran1..10 / kharej1..10)
# ----------------------------------------------------------------------------

def uninstall_flow():
    banner("حذف تانل")
    tunnels = list_tunnels_table()
    if not tunnels:
        pause()
        return
    hr()
    info("می‌توانید چند شماره را با کاما جدا از هم وارد کنید (مثال: 1,3,4) یا all برای حذف همه.")
    raw = prompt_str("شماره‌ی تانل(های) مورد نظر برای حذف (۰ برای بازگشت)")
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
                warn(f"مقدار نامعتبر نادیده گرفته شد: {part}")
        targets = [tunnels[i - 1] for i in indices]

    if not targets:
        warn("هیچ تانل معتبری انتخاب نشد.")
        pause()
        return

    print(f"{C.RED}موارد زیر برای همیشه حذف خواهند شد:{C.RESET}")
    for t in targets:
        print(f"  - {t['name']} ({t['role']}, {t['transport']})")

    if not prompt_yes_no("آیا مطمئن هستید؟ این عملیات قابل بازگشت نیست.", default=False):
        warn("عملیات لغو شد.")
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
        ok(f"تانل «{t['name']}» حذف شد.")

    pause()


# ----------------------------------------------------------------------------
# مانیتورینگ ترافیک پورت (tcpdump)
# ----------------------------------------------------------------------------

def monitor_flow():
    banner("مانیتورینگ ترافیک (TCPdump)")
    tunnels = list_tunnels_table()
    if not tunnels:
        pause()
        return
    hr()
    idx = prompt_int("شماره‌ی تانل مورد نظر (۰ برای بازگشت)", min_val=0, max_val=len(tunnels))
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
        warn("پورتی برای این تانل پیدا نشد.")
        pause()
        return

    duration = prompt_int("مدت مانیتورینگ (ثانیه)", default=10, min_val=1, max_val=300)
    port_filter = " or ".join(f"port {p}" for p in ports)
    info(f"در حال مانیتور پورت‌ها: {sorted(ports)} به مدت {duration} ثانیه...")
    result = run(f"timeout {duration} tcpdump -i any -n -q {port_filter}", capture=True)
    if result and hasattr(result, "stdout"):
        lines = (result.stdout or "").strip().splitlines()
        print(f"{C.WHITE}تعداد بسته‌های دیده‌شده: {len(lines)}{C.RESET}")
    pause()


# ----------------------------------------------------------------------------
# منوها
# ----------------------------------------------------------------------------

def create_menu():
    banner("ساخت تانل جدید")
    choice = prompt_choice("نقش این سرور را انتخاب کنید:", [
        ("1", "سرور ایران (Server)"),
        ("2", "کلاینت خارج (Client)"),
    ])
    if choice is None:
        return
    role = "server" if choice == "1" else "client"
    create_tunnel_flow(role)


def update_binary_menu():
    banner("به‌روزرسانی باینری Backhaul")
    download_binary(force_update=True)
    pause()


def main_menu():
    ensure_dirs()
    while True:
        banner("منوی اصلی")
        hr()
        options = [
            ("1", "ساخت تانل جدید"),
            ("2", "وضعیت تانل‌ها"),
            ("3", "ویرایش تانل"),
            ("4", "حذف تانل"),
            ("5", "مانیتورینگ ترافیک (TCPdump)"),
            ("6", "بررسی/آپدیت باینری Backhaul"),
        ]
        for key, desc in options:
            print(f"  {C.GREEN}{key}{C.RESET})  {desc}")
        print(f"  {C.RED}0{C.RESET})  خروج")
        hr()
        try:
            choice = input(f"{C.PINK}انتخاب شما: {C.RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            ok("خدانگهدار!")
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
            ok("خدانگهدار!")
            break
        else:
            warn("گزینه نامعتبر است.")
            pause()


def main():
    require_root()
    try:
        main_menu()
    except KeyboardInterrupt:
        print()
        ok("خدانگهدار!")
        sys.exit(0)


if __name__ == "__main__":
    main()
