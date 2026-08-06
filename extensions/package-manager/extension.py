import asyncio
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
from pclink.core.extension_base import ExtensionBase
from fastapi import APIRouter

SYSTEM = platform.system().lower()
ARCH = platform.machine()

# ---------------------------------------------------------------------------
# Winget self-update: cascade through multiple strategies for fresh Windows
# ---------------------------------------------------------------------------

WINGET_SELF_STRATEGIES = [
    # 1. Normal update (works if winget is already registered)
    {"label": "winget upgrade --self", "cmd": ["winget", "upgrade", "--self", "--accept-source-agreements"]},
    # 2. Upgrade the App Installer package directly
    {"label": "winget upgrade DesktopAppInstaller", "cmd": ["winget", "upgrade", "Microsoft.DesktopAppInstaller", "--accept-source-agreements"]},
    # 3. Register via Appx (re-registers winget without Store, works if package exists)
    {"label": "Register winget via Appx", "cmd": ["powershell", "-NoProfile", "-Command",
        "Add-AppxPackage -RegisterByFamilyName -MainPackage Microsoft.DesktopAppInstaller_8wekyb3d8bbwe -ErrorAction Stop"]},
    # 4. Install from Microsoft Store URL
    {"label": "Install from Microsoft Store", "cmd": ["powershell", "-NoProfile", "-Command",
        "Add-AppxPackage https://aka.ms/getwinget -ErrorAction Stop"]},
    # 5. Download latest .msixbundle from GitHub releases
    {
        "label": "Download winget from GitHub releases",
        "cmd": None,
        "fallback_download": True,
        "hint": "Download latest .msixbundle from github.com/microsoft/winget-cli/releases"
    },
]

async def _winget_update_self():
    """Try each strategy until one succeeds."""
    for strategy in WINGET_SELF_STRATEGIES:
        if strategy.get("fallback_download"):
            return {
                "success": False,
                "error": "All automated methods failed. Download the latest .msixbundle from:",
                "label": strategy["label"],
                "download_url": "https://github.com/microsoft/winget-cli/releases/latest",
                "manual_hint": "Download the .msixbundle file, then run: Add-AppxPackage <file.msixbundle>"
            }
        stdout, stderr, rc = await _run(strategy["cmd"], timeout=180)
        if rc == 0:
            return {"success": True, "stdout": stdout[-3000:], "method": strategy["label"]}
    return {"success": False, "error": "All winget update/install methods failed", "methods_tried": [s["label"] for s in WINGET_SELF_STRATEGIES if s.get("cmd")]}


async def _repair_or_install_winget():
    """Full winget repair: detect, register, or download. Returns status of each step."""
    results = []
    steps = [
        ("Check if winget is accessible", lambda: shutil.which("winget") is not None),
        ("Register via Add-AppxPackage -RegisterByFamilyName", ["powershell", "-NoProfile", "-Command",
            "Add-AppxPackage -RegisterByFamilyName -MainPackage Microsoft.DesktopAppInstaller_8wekyb3d8bbwe -ErrorAction Stop"]),
        ("Install from aka.ms/getwinget (latest stable)", ["powershell", "-NoProfile", "-Command",
            "Add-AppxPackage https://aka.ms/getwinget -ErrorAction Stop"]),
    ]
    for label, cmd in steps:
        if callable(cmd):
            results.append({"step": label, "success": cmd(), "output": "winget found on PATH" if cmd() else "winget not on PATH"})
            continue
        stdout, stderr, rc = await _run(cmd, timeout=180)
        results.append({"step": label, "success": rc == 0, "output": stdout[-500:] or stderr[-500:]})
    # Final check
    found = shutil.which("winget") is not None
    return {"success": found, "steps": results}

# ---------------------------------------------------------------------------
# Package manager definitions
# ---------------------------------------------------------------------------

PM_DEFS = [
    # -- Windows --
    {
        "id": "winget", "display": "Winget", "platforms": ["windows"],
        "detect": lambda: shutil.which("winget") is not None,
        "install_hint": 'Built into Windows 10 1709+ / 11. Use "Repair Winget" endpoint if missing.',
        "update_self": "cascade:_winget",
        "update_all": ["winget", "upgrade", "--all", "--accept-source-agreements"],
        "list_cmd": ["winget", "upgrade"],
        "upgrade_one": lambda pkg: ["winget", "upgrade", "--id", pkg, "--accept-source-agreements"],
        "install_one": lambda pkg: ["winget", "install", "--id", pkg, "--accept-source-agreements"],
        "search_cmd": lambda q: ["winget", "search", q, "--accept-source-agreements"],
        "parse_outdated": _parse_winget_outdated,
        "parse_search": _parse_winget_search,
    },
    {
        "id": "choco", "display": "Chocolatey", "platforms": ["windows"],
        "detect": lambda: shutil.which("choco") is not None,
        "install_hint": 'PowerShell: Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = 3072; iex ((New-Object System.Net.WebClient).DownloadString("https://chocolatey.org/install.ps1"))',
        "install_cmd": ["powershell", "-NoProfile", "-Command",
                        "Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"],
        "update_self": ["choco", "upgrade", "chocolatey", "-y"],
        "update_all": ["choco", "upgrade", "all", "-y"],
        "list_cmd": ["choco", "outdated", "-r"],
        "upgrade_one": lambda pkg: ["choco", "upgrade", pkg, "-y"],
        "install_one": lambda pkg: ["choco", "install", pkg, "-y"],
        "search_cmd": lambda q: ["choco", "find", q, "--limit", "30"],
        "parse_outdated": _parse_choco_outdated,
        "parse_search": _parse_choco_search,
    },
    {
        "id": "scoop", "display": "Scoop", "platforms": ["windows"],
        "detect": lambda: shutil.which("scoop") is not None,
        "install_hint": 'PowerShell: iex "& {$(irm get.scoop.sh)} -RunAsAdmin"',
        "install_cmd": ["powershell", "-NoProfile", "-Command", 'iex "& {$(irm get.scoop.sh)} -RunAsAdmin"'],
        "update_self": ["scoop", "update"],
        "update_all": ["scoop", "update", "--all"],
        "list_cmd": ["scoop", "status"],
        "upgrade_one": lambda pkg: ["scoop", "update", pkg],
        "install_one": lambda pkg: ["scoop", "install", pkg],
        "search_cmd": lambda q: ["scoop", "search", q],
        "parse_outdated": _parse_scoop_outdated,
        "parse_search": _parse_scoop_search,
    },
    # -- Linux --
    {
        "id": "apt", "display": "APT", "platforms": ["linux"],
        "detect": lambda: shutil.which("apt") is not None,
        "install_hint": "Pre-installed on Debian/Ubuntu-based distros",
        "update_self": ["apt", "update"],
        "update_all": ["apt", "upgrade", "-y"],
        "list_cmd": ["apt", "list", "--upgradable"],
        "upgrade_one": lambda pkg: ["apt", "install", "--only-upgrade", "-y", pkg.split("/")[0].strip()],
        "install_one": lambda pkg: ["apt", "install", "-y", pkg],
        "search_cmd": lambda q: ["apt-cache", "search", q],
        "parse_outdated": _parse_apt_outdated,
        "parse_search": _parse_apt_search,
        "needs_sudo": True,
    },
    {
        "id": "pacman", "display": "Pacman", "platforms": ["linux"],
        "detect": lambda: shutil.which("pacman") is not None,
        "install_hint": "Pre-installed on Arch Linux",
        "update_self": ["pacman", "-Sy"],
        "update_all": ["pacman", "-Su", "--noconfirm"],
        "list_cmd": ["pacman", "-Qu"],
        "upgrade_one": lambda pkg: ["pacman", "-S", "--noconfirm", pkg.split()[0]],
        "install_one": lambda pkg: ["pacman", "-S", "--noconfirm", pkg],
        "search_cmd": lambda q: ["pacman", "-Ss", q],
        "parse_outdated": _parse_pacman_outdated,
        "parse_search": _parse_pacman_search,
        "needs_sudo": True,
    },
    {
        "id": "dnf", "display": "DNF", "platforms": ["linux"],
        "detect": lambda: shutil.which("dnf") is not None,
        "install_hint": "Pre-installed on Fedora",
        "update_self": ["dnf", "makecache"],
        "update_all": ["dnf", "upgrade", "-y"],
        "list_cmd": ["dnf", "check-update"],
        "upgrade_one": lambda pkg: ["dnf", "upgrade", "-y", pkg.split(".")[0].strip()],
        "install_one": lambda pkg: ["dnf", "install", "-y", pkg],
        "search_cmd": lambda q: ["dnf", "search", q],
        "parse_outdated": _parse_dnf_outdated,
        "parse_search": _parse_dnf_search,
        "needs_sudo": True,
    },
    {
        "id": "snap", "display": "Snap", "platforms": ["linux"],
        "detect": lambda: shutil.which("snap") is not None,
        "install_hint": "sudo apt install snapd | sudo dnf install snapd",
        "install_cmd": ["apt", "install", "-y", "snapd"],
        "update_self": ["snap", "refresh", "core"],
        "update_all": ["snap", "refresh"],
        "list_cmd": ["snap", "refresh", "--list"],
        "upgrade_one": lambda pkg: ["snap", "refresh", pkg.strip()],
        "install_one": lambda pkg: ["snap", "install", pkg],
        "search_cmd": lambda q: ["snap", "find", q],
        "parse_outdated": _parse_snap_outdated,
        "parse_search": _parse_snap_search,
    },
    {
        "id": "flatpak", "display": "Flatpak", "platforms": ["linux"],
        "detect": lambda: shutil.which("flatpak") is not None,
        "install_hint": "sudo apt install flatpak | sudo dnf install flatpak",
        "install_cmd": ["apt", "install", "-y", "flatpak"],
        "update_self": None,
        "update_all": ["flatpak", "update", "-y"],
        "list_cmd": ["flatpak", "update", "--dry-run"],
        "upgrade_one": lambda pkg: ["flatpak", "update", "-y", pkg.strip()],
        "install_one": lambda pkg: ["flatpak", "install", "-y", pkg],
        "search_cmd": lambda q: ["flatpak", "search", q],
        "parse_outdated": _parse_flatpak_outdated,
        "parse_search": _parse_flatpak_search,
    },
    # -- macOS --
    {
        "id": "brew", "display": "Homebrew", "platforms": ["darwin"],
        "detect": lambda: shutil.which("brew") is not None,
        "install_hint": '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
        "install_cmd": ["/bin/bash", "-c", "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"],
        "update_self": ["brew", "update"],
        "update_all": ["brew", "upgrade"],
        "list_cmd": ["brew", "outdated"],
        "upgrade_one": lambda pkg: ["brew", "upgrade", pkg.split()[0]],
        "install_one": lambda pkg: ["brew", "install", pkg],
        "search_cmd": lambda q: ["brew", "search", q],
        "parse_outdated": _parse_brew_outdated,
        "parse_search": _parse_brew_search,
    },
    {
        "id": "mas", "display": "Mac App Store", "platforms": ["darwin"],
        "detect": lambda: shutil.which("mas") is not None,
        "install_hint": "brew install mas",
        "install_cmd": ["brew", "install", "mas"],
        "update_self": None,
        "update_all": ["mas", "upgrade"],
        "list_cmd": ["mas", "outdated"],
        "upgrade_one": lambda pkg: ["mas", "upgrade", pkg.split()[0]],
        "install_one": lambda pkg: ["mas", "install", pkg],
        "search_cmd": lambda q: ["mas", "search", q],
        "parse_outdated": _parse_mas_outdated,
        "parse_search": _parse_mas_search,
    },
    {
        "id": "macports", "display": "MacPorts", "platforms": ["darwin"],
        "detect": lambda: shutil.which("port") is not None,
        "install_hint": "https://www.macports.org/install.php",
        "update_self": ["port", "selfupdate"],
        "update_all": ["port", "upgrade", "outdated"],
        "list_cmd": ["port", "outdated"],
        "upgrade_one": lambda pkg: ["port", "upgrade", pkg.split()[0]],
        "install_one": lambda pkg: ["port", "install", pkg],
        "search_cmd": lambda q: ["port", "search", q],
        "parse_outdated": _parse_macports_outdated,
        "parse_search": _parse_macports_search,
    },
]

# ---------------------------------------------------------------------------
# Outdated package parsers
# ---------------------------------------------------------------------------

def _parse_winget_outdated(stdout):
    pkgs = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0] != "Name":
            pkgs.append({"name": parts[0], "id": parts[1], "installed": parts[2], "available": parts[3]})
    return pkgs

def _parse_choco_outdated(stdout):
    pkgs = []
    for line in stdout.splitlines():
        parts = line.split("|")
        if len(parts) >= 3:
            pkgs.append({"name": parts[0].strip(), "id": parts[0].strip(), "installed": parts[1].strip(), "available": parts[2].strip()})
    return pkgs

def _parse_scoop_outdated(stdout):
    pkgs = []
    started = False
    for line in stdout.splitlines():
        if "Updates are available for" in line:
            started = True; continue
        if not started: continue
        m = re.match(r"(\S+)\s+.*\((\S+)\s*->\s*(\S+)\)", line)
        if m: pkgs.append({"name": m.group(1), "id": m.group(1), "installed": m.group(2), "available": m.group(3)})
    return pkgs

def _parse_apt_outdated(stdout):
    pkgs = []
    for line in stdout.splitlines():
        if "/" in line and "upgradable" in line:
            name = line.split("/")[0]
            m = re.search(r"(\S+)\s+(\S+)\s+(\S+)", line)
            if m: pkgs.append({"name": name, "id": name, "installed": m.group(2), "available": m.group(3)})
    return pkgs

def _parse_pacman_outdated(stdout):
    pkgs = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2: pkgs.append({"name": parts[0], "id": parts[0], "installed": parts[1] if len(parts) > 1 else "?", "available": parts[2] if len(parts) > 2 else "?"})
    return pkgs

def _parse_dnf_outdated(stdout):
    pkgs = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and "." in parts[0]:
            pkgs.append({"name": parts[0].split(".")[0], "id": parts[0], "installed": parts[1], "available": parts[2]})
    return pkgs

def _parse_snap_outdated(stdout):
    pkgs = []
    for line in stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 3: pkgs.append({"name": parts[0], "id": parts[0], "installed": parts[1], "available": parts[2]})
    return pkgs

def _parse_flatpak_outdated(stdout):
    pkgs = []
    for line in stdout.splitlines():
        if "\t" in line:
            parts = line.strip().split("\t")
            if len(parts) >= 2: pkgs.append({"name": parts[1].strip(), "id": parts[0].strip(), "installed": parts[2].strip() if len(parts) > 2 else "?", "available": "?"})
    return pkgs

def _parse_brew_outdated(stdout):
    pkgs = []
    for line in stdout.splitlines():
        parts = line.split()
        if parts: pkgs.append({"name": parts[0], "id": parts[0], "installed": parts[1] if len(parts) > 1 else "?", "available": parts[2] if len(parts) > 2 else "?"})
    return pkgs

def _parse_mas_outdated(stdout):
    pkgs = []
    for line in stdout.splitlines():
        m = re.match(r"(\d+)\s+(.+)", line)
        if m: pkgs.append({"name": m.group(2).strip(), "id": m.group(1), "installed": "?", "available": "?"})
    return pkgs

def _parse_macports_outdated(stdout):
    pkgs = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2: pkgs.append({"name": parts[0], "id": parts[0], "installed": parts[1], "available": parts[2] if len(parts) > 2 else "?"})
    return pkgs

# ---------------------------------------------------------------------------
# Search result parsers
# ---------------------------------------------------------------------------

def _parse_winget_search(stdout):
    pkgs = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] not in ("Name", "--"):
            pkgs.append({"name": parts[0], "id": parts[0], "version": parts[2] if len(parts) > 2 else "?"})
    return pkgs

def _parse_choco_search(stdout):
    pkgs = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] != "Chocolatey":
            pkgs.append({"name": parts[0], "id": parts[0], "version": parts[1].strip("()") if len(parts) > 1 else "?"})
    return pkgs

def _parse_scoop_search(stdout):
    pkgs = []
    in_results = False
    for line in stdout.splitlines():
        if "'main' bucket:" in line: in_results = True; continue
        if in_results and line.strip():
            parts = line.split()
            if parts: pkgs.append({"name": parts[0], "id": parts[0], "version": parts[1] if len(parts) > 1 else "?"})
    if not pkgs:
        for line in stdout.splitlines():
            m = re.match(r"(\S+)\s+\(.*\)", line)
            if m: pkgs.append({"name": m.group(1), "id": m.group(1), "version": "?"})
    return pkgs

def _parse_apt_search(stdout):
    pkgs = []
    for line in stdout.splitlines():
        m = re.match(r"(\S+)\s+-\s+(.+)", line)
        if m: pkgs.append({"name": m.group(1).strip(), "id": m.group(1).strip(), "version": m.group(2)[:60]})
    return pkgs

def _parse_pacman_search(stdout):
    pkgs = []
    for line in stdout.splitlines():
        m = re.match(r"(\S+)/(\S+)\s+(.*)", line)
        if m: pkgs.append({"name": m.group(2), "id": f"{m.group(1)}/{m.group(2)}", "version": m.group(3).split()[0] if m.group(3) else "?"})
    return pkgs

def _parse_dnf_search(stdout):
    pkgs = []
    for line in stdout.splitlines():
        m = re.match(r"(\S+\.\S+)\s+:\s+(.+)", line)
        if m: pkgs.append({"name": m.group(1).split(".")[0], "id": m.group(1), "version": m.group(2)[:60]})
    return pkgs

def _parse_snap_search(stdout):
    pkgs = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] not in ("Name", "--"):
            pkgs.append({"name": parts[0], "id": parts[0], "version": parts[1]})
    return pkgs

def _parse_flatpak_search(stdout):
    pkgs = []
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            m = re.search(r"(\S+)\s+(\S+)", parts[0])
            if m: pkgs.append({"name": m.group(1), "id": m.group(1), "version": m.group(2)})
    return pkgs

def _parse_brew_search(stdout):
    pkgs = []
    for line in stdout.splitlines():
        parts = line.split()
        if parts and "/" not in parts[0]:
            pkgs.append({"name": parts[0], "id": parts[0], "version": parts[1] if len(parts) > 1 else "?"})
    return pkgs

def _parse_mas_search(stdout):
    pkgs = []
    for line in stdout.splitlines():
        m = re.match(r"(\d+)\s+(.+)", line)
        if m: pkgs.append({"name": m.group(2).strip(), "id": m.group(1), "version": "?"})
    return pkgs

def _parse_macports_search(stdout):
    pkgs = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            pkgs.append({"name": parts[0], "id": parts[0], "version": parts[1]})
    return pkgs

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _run(cmd, timeout=120):
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode(errors="replace"), stderr.decode(errors="replace"), proc.returncode
    except asyncio.TimeoutError:
        if proc: proc.kill(); await proc.wait()
        return "", "TIMEOUT", -1
    except FileNotFoundError:
        return "", "COMMAND_NOT_FOUND", -1
    except Exception as e:
        return "", str(e), -1

def _filter_platform(pm):
    return SYSTEM in pm["platforms"]

def _needs_sudo(pm):
    return pm.get("needs_sudo", False) and os.geteuid() != 0

async def _run_for_pm(pm, cmd, timeout=120):
    if _needs_sudo(pm):
        cmd = ["sudo"] + cmd
    return await _run(cmd, timeout=timeout)

def _find_pm(pm_id):
    return next((p for p in PM_DEFS if p["id"] == pm_id and _filter_platform(p)), None)

# ---------------------------------------------------------------------------
# Extension
# ---------------------------------------------------------------------------

class Extension(ExtensionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_routes()

    def setup_routes(self):
        @self.router.get("/managers")
        async def get_managers():
            results = []
            for pm in PM_DEFS:
                if not _filter_platform(pm): continue
                detected = pm["detect"]()
                results.append({
                    "id": pm["id"], "display": pm["display"],
                    "detected": detected,
                    "install_hint": pm.get("install_hint", ""),
                    "can_update_self": pm.get("update_self") is not None,
                    "can_search": pm.get("search_cmd") is not None,
                })
            return {"managers": results, "platform": SYSTEM, "arch": ARCH}

        # -- Outdated list --
        @self.router.get("/outdated/{pm_id}")
        async def list_outdated(pm_id: str):
            pm = _find_pm(pm_id)
            if not pm: return {"success": False, "error": "Unsupported"}
            if not pm["detect"](): return {"success": False, "error": "Package manager not installed"}
            stdout, stderr, rc = await _run_for_pm(pm, pm["list_cmd"])
            if rc not in (0, 1): return {"success": False, "error": stderr or stdout}
            try: pkgs = pm["parse_outdated"](stdout)
            except Exception: pkgs = []
            return {"success": True, "packages": pkgs}

        # -- Search --
        @self.router.get("/search/{pm_id}/{query:path}")
        async def search_packages(pm_id: str, query: str):
            pm = _find_pm(pm_id)
            if not pm: return {"success": False, "error": "Unsupported"}
            if not pm.get("search_cmd"): return {"success": False, "error": "Search not supported"}
            cmd = pm["search_cmd"](query)
            stdout, stderr, rc = await _run_for_pm(pm, cmd)
            try: pkgs = pm["parse_search"](stdout)
            except Exception: pkgs = []
            return {"success": True, "packages": pkgs}

        # -- Install a new package --
        @self.router.post("/install/{pm_id}")
        async def install_package(pm_id: str, data: dict):
            pm = _find_pm(pm_id)
            if not pm: return {"success": False, "error": "Unsupported"}
            pkg = data.get("package", "").strip()
            if not pkg: return {"success": False, "error": "No package specified"}
            cmd = pm["install_one"](pkg)
            stdout, stderr, rc = await _run_for_pm(pm, cmd, timeout=300)
            return {"success": rc == 0, "stdout": stdout[-3000:], "stderr": stderr[-3000:], "returncode": rc}

        # -- Upgrade a single package --
        @self.router.post("/upgrade/{pm_id}")
        async def upgrade_package(pm_id: str, data: dict):
            pm = _find_pm(pm_id)
            if not pm: return {"success": False, "error": "Unsupported"}
            pkg = data.get("package", "")
            if not pkg: return {"success": False, "error": "No package specified"}
            cmd = pm["upgrade_one"](pkg)
            stdout, stderr, rc = await _run_for_pm(pm, cmd)
            return {"success": rc == 0, "stdout": stdout[-2000:], "stderr": stderr[-2000:], "returncode": rc}

        # -- Upgrade all --
        @self.router.post("/upgrade-all/{pm_id}")
        async def upgrade_all(pm_id: str):
            pm = _find_pm(pm_id)
            if not pm: return {"success": False, "error": "Unsupported"}
            stdout, stderr, rc = await _run_for_pm(pm, pm["update_all"], timeout=600)
            return {"success": rc == 0, "stdout": stdout[-3000:], "stderr": stderr[-3000:], "returncode": rc}

        # -- Upgrade selected --
        @self.router.post("/upgrade-selected/{pm_id}")
        async def upgrade_selected(pm_id: str, data: dict):
            pm = _find_pm(pm_id)
            if not pm: return {"success": False, "error": "Unsupported"}
            pkgs = data.get("packages", [])
            results = []
            for pkg in pkgs:
                cmd = pm["upgrade_one"](pkg)
                stdout, stderr, rc = await _run_for_pm(pm, cmd, timeout=300)
                results.append({"package": pkg, "success": rc == 0, "stderr": stderr[-500:]})
            return {"success": True, "results": results}

        # -- Update package manager itself --
        @self.router.post("/update-self/{pm_id}")
        async def update_self(pm_id: str):
            pm = _find_pm(pm_id)
            if not pm: return {"success": False, "error": "Unsupported"}
            strat = pm.get("update_self")
            if strat is None: return {"success": False, "error": "Not supported"}

            # Cascade strategy (winget)
            if isinstance(strat, str) and strat.startswith("cascade:"):
                if strat == "cascade:_winget":
                    return await _winget_update_self()
                return {"success": False, "error": "Unknown cascade"}

            # Standard command
            stdout, stderr, rc = await _run_for_pm(pm, strat, timeout=300)
            return {"success": rc == 0, "stdout": stdout[-2000:], "stderr": stderr[-2000:], "returncode": rc}

        # -- Repair/install winget (fresh Windows builds) --
        @self.router.post("/repair-winget")
        async def repair_winget():
            if SYSTEM != "windows":
                return {"success": False, "error": "Windows only"}
            return await _repair_or_install_winget()

        # -- Install a package manager --
        @self.router.post("/install-manager/{pm_id}")
        async def install_manager(pm_id: str):
            pm = _find_pm(pm_id)
            if not pm or not pm.get("install_cmd"):
                return {"success": False, "error": "No install method available"}
            stdout, stderr, rc = await _run(pm["install_cmd"], timeout=600)
            return {"success": rc == 0, "stdout": stdout[-3000:], "stderr": stderr[-3000:], "returncode": rc}

    def initialize(self) -> bool:
        return True

    def cleanup(self):
        pass

    def get_routes(self) -> APIRouter:
        return self.router

