import os
import sys
import re
import platform
import shutil
import zipfile
import threading
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

class SessionConfig(BaseModel):
    device_id: str
    width: int = 1920
    height: int = 1080
    dpi: int = 240
    fps: int = 60

class LaunchAppRequest(BaseModel):
    device_id: str
    package: str
    activity: str


class Extension:
    """PCLink Manifest v2 Backend Worker for Android Desktop Workspace."""

    def __init__(self):
        self.app = FastAPI(title="Android Desktop Workspace Extension")
        self.base_dir = Path(__file__).resolve().parent
        self.bin_dir = self.base_dir / "bin"
        self.bin_dir.mkdir(exist_ok=True)

        self.state: Dict[str, Any] = {
            "scrcpy_proc": None,
            "active_device": None,
            "active_display_id": 0,
            "download_status": "idle",
            "download_progress": 0
        }

        self._setup_middleware()
        self._setup_routes()

    async def __call__(self, scope, receive, send):
        """Allows PCLink to invoke Extension directly as an ASGI application."""
        await self.app(scope, receive, send)

    def _setup_middleware(self):
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # --- Utility: Binary Discovery ---

    def _get_bin(self, name: str) -> Optional[str]:
        ext = ".exe" if platform.system() == "Windows" else ""
        local_direct = self.bin_dir / f"{name}{ext}"
        if local_direct.is_file():
            return str(local_direct)

        matches = list(self.bin_dir.glob(f"**/{name}{ext}"))
        if matches:
            return str(matches[0])

        return shutil.which(name)

    def _run_adb(self, device_id: str, args: list[str]) -> str:
        adb_bin = self._get_bin("adb")
        if not adb_bin:
            raise HTTPException(status_code=500, detail="ADB binary not found on host.")
        cmd = [adb_bin, "-s", device_id] + args
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise HTTPException(status_code=400, detail=res.stderr.strip() or res.stdout.strip())
        return res.stdout.strip()

    # --- Routes ---

    def _setup_routes(self):

        @self.app.get("/api/system/audit")
        def audit_environment():
            sys_name = platform.system()
            arch = platform.machine()
            adb_path = self._get_bin("adb")
            scrcpy_path = self._get_bin("scrcpy")

            return {
                "os": sys_name,
                "arch": arch,
                "adb_installed": adb_path is not None,
                "scrcpy_installed": scrcpy_path is not None,
                "adb_path": adb_path,
                "scrcpy_path": scrcpy_path,
                "download_status": self.state["download_status"],
                "download_progress": self.state["download_progress"]
            }

        @self.app.post("/api/system/install-binaries")
        def install_binaries():
            if platform.system() != "Windows":
                return {
                    "status": "manual",
                    "message": "On Linux run 'sudo apt install scrcpy adb'. On macOS run 'brew install scrcpy android-platform-tools'."
                }

            if self.state["download_status"] == "downloading":
                return {"status": "in_progress"}

            # Scrcpy official Windows release includes adb.exe
            url = "https://github.com/Genymobile/scrcpy/releases/download/v2.4/scrcpy-win64-v2.4.zip"
            zip_dest = self.bin_dir / "scrcpy.zip"

            def worker():
                import urllib.request
                try:
                    self.state["download_status"] = "downloading"

                    def report(block_num, block_size, total_size):
                        if total_size > 0:
                            percent = int((block_num * block_size / total_size) * 100)
                            self.state["download_progress"] = min(percent, 99)

                    urllib.request.urlretrieve(url, zip_dest, reporthook=report)

                    self.state["download_status"] = "extracting"
                    with zipfile.ZipFile(zip_dest, "r") as z:
                        z.extractall(self.bin_dir)

                    zip_dest.unlink(missing_ok=True)
                    self.state["download_status"] = "ready"
                    self.state["download_progress"] = 100
                except Exception as ex:
                    self.state["download_status"] = f"failed: {str(ex)}"

            t = threading.Thread(target=worker, daemon=True)
            t.start()
            return {"status": "started"}

        @self.app.get("/api/devices")
        def list_devices():
            adb = self._get_bin("adb")
            if not adb:
                return {"devices": []}

            res = subprocess.run([adb, "devices", "-l"], capture_output=True, text=True)
            devices = []
            for line in res.stdout.strip().split("\n")[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                serial = parts[0]
                state_str = parts[1]
                model = "Android Device"

                for p in parts:
                    if p.startswith("model:"):
                        model = p.replace("model:", "").replace("_", " ")

                if state_str == "device":
                    try:
                        ver_out = self._run_adb(serial, ["shell", "getprop", "ro.build.version.release"])
                    except Exception:
                        ver_out = "Unknown"

                    devices.append({
                        "serial": serial,
                        "model": model,
                        "state": state_str,
                        "android_version": ver_out
                    })
            return {"devices": devices}

        @self.app.post("/api/desktop/start")
        def start_desktop_session(config: SessionConfig):
            if self.state["scrcpy_proc"] is not None and self.state["scrcpy_proc"].poll() is None:
                return {"status": "active", "message": "Session already active."}

            scrcpy_bin = self._get_bin("scrcpy")
            if not scrcpy_bin:
                raise HTTPException(status_code=500, detail="Scrcpy binary not found.")

            self.state["active_device"] = config.device_id

            # 1. Enable Global Freeform Multitasking
            self._run_adb(config.device_id, ["shell", "settings", "put", "global", "enable_freeform_support", "1"])
            self._run_adb(config.device_id, ["shell", "settings", "put", "global", "force_resizable_activities", "1"])

            # 2. Command Scrcpy to allocate an independent headless virtual display
            cmd = [
                scrcpy_bin,
                "-s", config.device_id,
                f"--new-display={config.width}x{config.height}/{config.dpi}",
                "--audio-source=playback",
                "--video-bit-rate=16M",
                f"--max-fps={config.fps}",
                "--window-title=Android Desktop Workspace",
                "--stay-awake"
            ]

            self.state["scrcpy_proc"] = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Discover the allocated virtual display ID from scrcpy logs
            def parse_display_id():
                for line in self.state["scrcpy_proc"].stdout:
                    match = re.search(r"display.*?id[=:]\s*(\d+)", line, re.IGNORECASE)
                    if match:
                        self.state["active_display_id"] = int(match.group(1))
                        break

            threading.Thread(target=parse_display_id, daemon=True).start()
            return {"status": "started", "device": config.device_id}

        @self.app.get("/api/desktop/apps")
        def get_installed_apps(device_id: str):
            out = self._run_adb(device_id, [
                "shell", "cmd", "package", "query-activities",
                "-a", "android.intent.action.MAIN",
                "-c", "android.intent.category.LAUNCHER"
            ])
            apps = []
            cur_pkg = None

            for line in out.splitlines():
                line = line.strip()
                if "packageName=" in line:
                    cur_pkg = line.split("packageName=")[-1]
                elif "name=" in line and cur_pkg:
                    act = line.split("name=")[-1]
                    label = cur_pkg.split(".")[-1].capitalize()
                    apps.append({"package": cur_pkg, "activity": act, "label": label})
                    cur_pkg = None

            return {"apps": apps}

        @self.app.post("/api/desktop/launch-app")
        def launch_app(req: LaunchAppRequest):
            disp = self.state["active_display_id"]
            # WindowingMode 5 = Freeform window
            cmd = [
                "shell", "am", "start",
                "-n", f"{req.package}/{req.activity}",
                "--display", str(disp),
                "--windowingMode", "5",
                "-N"
            ]
            res = self._run_adb(req.device_id, cmd)
            return {"status": "launched", "output": res}

        @self.app.post("/api/desktop/stop")
        def stop_desktop_session():
            if self.state["scrcpy_proc"]:
                self.state["scrcpy_proc"].terminate()
                self.state["scrcpy_proc"] = None
                self.state["active_device"] = None
                self.state["active_display_id"] = 0
            return {"status": "stopped"}
