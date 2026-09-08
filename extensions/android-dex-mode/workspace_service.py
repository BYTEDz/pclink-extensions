import asyncio
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .adb_service import AdbService
    from .binary_manager import BinaryManager
except (ImportError, ValueError):
    from adb_service import AdbService
    from binary_manager import BinaryManager

log = logging.getLogger(__name__)


class WorkspaceService:
    def __init__(self, binary_manager: BinaryManager, adb_service: AdbService):
        self.bin_mgr = binary_manager
        self.adb = adb_service
        self.active_session: Optional[Dict[str, Any]] = None
        self._scrcpy_process: Optional[subprocess.Popen] = None
        self._scrcpy_features: Optional[Dict[str, Any]] = None
        self._used_overlay_devices: bool = False
        self._lock = threading.Lock()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            is_running = self._scrcpy_process is not None and self._scrcpy_process.poll() is None
            return {
                "active": is_running,
                "session": self.active_session if is_running else None,
                "binaries": self.bin_mgr.check_binaries(),
            }

    async def _probe_scrcpy_features(self, scrcpy_bin: str) -> Dict[str, Any]:
        if self._scrcpy_features is not None:
            return self._scrcpy_features

        features = {
            "display_flag": "--display",
            "has_new_display": False,
            "has_no_audio": False,
            "has_max_fps": False,
            "has_window_title": False,
            "has_shortcut_mod": False,
            "has_forward_all_clicks": False,
        }

        try:
            proc = await asyncio.create_subprocess_exec(
                scrcpy_bin, "--help",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await proc.communicate()
            help_text = (stdout_b + stderr_b).decode("utf-8", errors="ignore")

            features["has_new_display"] = "--new-display" in help_text
            features["display_flag"] = "--display-id" if "--display-id" in help_text else "--display"
            features["has_no_audio"] = "--no-audio" in help_text
            features["has_max_fps"] = "--max-fps" in help_text
            features["has_window_title"] = "--window-title" in help_text
            features["has_shortcut_mod"] = "--shortcut-mod" in help_text
            features["has_forward_all_clicks"] = "--forward-all-clicks" in help_text
        except Exception as e:
            log.warning(f"Failed to probe scrcpy capabilities: {e}")

        self._scrcpy_features = features
        return features

    def _prepare_gui_environment(self) -> Dict[str, str]:
        env = os.environ.copy()

        if "DISPLAY" not in env:
            for display_candidate in [":0", ":1", ":0.0"]:
                socket_path = f"/tmp/.X11-unix/X{display_candidate.split(':')[1].split('.')[0]}"
                if os.path.exists(socket_path):
                    env["DISPLAY"] = display_candidate
                    break

        if "XAUTHORITY" not in env:
            home = Path.home()
            for xauth_candidate in [
                home / ".Xauthority",
                Path(f"/run/user/{os.getuid()}/gdm/Xauthority") if hasattr(os, "getuid") else None,
            ]:
                if xauth_candidate and xauth_candidate.exists():
                    env["XAUTHORITY"] = str(xauth_candidate)
                    break

        if "XDG_RUNTIME_DIR" not in env and hasattr(os, "getuid"):
            runtime_dir = f"/run/user/{os.getuid()}"
            if os.path.exists(runtime_dir):
                env["XDG_RUNTIME_DIR"] = runtime_dir

        if "WAYLAND_DISPLAY" not in env and "XDG_RUNTIME_DIR" in env:
            wayland_socket = f"{env['XDG_RUNTIME_DIR']}/wayland-0"
            if os.path.exists(wayland_socket):
                env["WAYLAND_DISPLAY"] = "wayland-0"

        return env

    def _cleanup_device_overlay_sync(self, target: str) -> None:
        if not self._used_overlay_devices:
            return

        adb_bin = self.bin_mgr.resolve_adb_path()
        if not adb_bin:
            return

        try:
            subprocess.run(
                [adb_bin, "-s", target, "shell", "settings", "put", "global", "overlay_display_devices", "null"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5.0,
            )
            log.info(f"Cleaned up overlay display on device {target}.")
        except Exception as e:
            log.warning(f"Failed to clean up overlay display on {target}: {e}")

    def _monitor_scrcpy_thread(self, proc: subprocess.Popen, target: str) -> None:
        def _stream_reader(stream, prefix):
            try:
                for line in iter(stream.readline, ""):
                    if not line:
                        break
                    clean_line = line.strip()
                    if clean_line:
                        log.info(f"[SCRCPY {prefix}] {clean_line}")
            except Exception:
                pass
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        t_out = threading.Thread(target=_stream_reader, args=(proc.stdout, "OUT"), daemon=True)
        t_err = threading.Thread(target=_stream_reader, args=(proc.stderr, "ERR"), daemon=True)
        t_out.start()
        t_err.start()

        return_code = proc.wait()
        log.info(f"Scrcpy workspace process for {target} exited with return code {return_code}.")

        with self._lock:
            if self._scrcpy_process == proc:
                self._scrcpy_process = None
                self.active_session = None

        self._cleanup_device_overlay_sync(target)

    async def start_workspace(
        self,
        ip: str,
        port: int = 5555,
        width: int = 1920,
        height: int = 1080,
        dpi: int = 210,
        bitrate_mbps: int = 16,
        max_fps: int = 60,
    ) -> Dict[str, Any]:
        with self._lock:
            if self._scrcpy_process and self._scrcpy_process.poll() is None:
                return {"success": True, "message": "Session already active.", "session": self.active_session}

        target = f"{ip}:{port}"
        connected, msg = await self.adb.connect(ip, port)
        if not connected:
            raise ConnectionError(f"Failed to connect via ADB to {target}: {msg}")

        await self.adb.configure_desktop_mode_flags(target)

        scrcpy_bin = self.bin_mgr.resolve_scrcpy_path()
        if not scrcpy_bin:
            raise FileNotFoundError("Scrcpy binary is missing.")

        features = await self._probe_scrcpy_features(scrcpy_bin)
        scrcpy_args = [scrcpy_bin, "-s", target]

        display_id = None
        if features["has_new_display"]:
            self._used_overlay_devices = False
            scrcpy_args.append(f"--new-display={width}x{height}/{dpi}")
            log.info("Starting headless virtual display via scrcpy --new-display.")
        else:
            self._used_overlay_devices = True
            created = await self.adb.create_overlay_display(target, width, height, dpi)
            if not created:
                raise RuntimeError("Failed to apply overlay display settings on device.")

            for _ in range(12):
                await asyncio.sleep(0.5)
                display_id = await self.adb.get_secondary_display_id(target)
                if display_id is not None:
                    break

            if display_id is None:
                await self.adb.destroy_overlay_display(target)
                raise RuntimeError("Virtual overlay display was created but display ID could not be resolved.")

            if features["display_flag"] == "--display-id":
                scrcpy_args.append(f"--display-id={display_id}")
            else:
                scrcpy_args.extend(["--display", str(display_id)])

        scrcpy_args.extend(["-b", f"{bitrate_mbps}M"])

        if features["has_max_fps"]:
            scrcpy_args.extend(["--max-fps", str(max_fps)])

        if features["has_window_title"]:
            scrcpy_args.extend(["--window-title", "PCLink Android DeX Mode"])

        if features["has_shortcut_mod"]:
            scrcpy_args.extend(["--shortcut-mod", "rctrl"])

        if features["has_forward_all_clicks"]:
            scrcpy_args.append("--forward-all-clicks")

        if features["has_no_audio"]:
            scrcpy_args.append("--no-audio")

        scrcpy_args.append("--stay-awake")

        gui_env = self._prepare_gui_environment()

        log.info(f"Spawning native scrcpy session: {' '.join(scrcpy_args)}")

        with self._lock:
            proc = subprocess.Popen(
                scrcpy_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=gui_env,
                text=True,
                bufsize=1,
            )
            self._scrcpy_process = proc

            self.active_session = {
                "ip": ip,
                "port": port,
                "target": target,
                "display_id": display_id,
                "resolution": f"{width}x{height}",
                "dpi": dpi,
                "pid": proc.pid,
                "headless_mode": features["has_new_display"],
            }

        monitor_thread = threading.Thread(
            target=self._monitor_scrcpy_thread,
            args=(proc, target),
            name=f"scrcpy-mon-{target}",
            daemon=True,
        )
        monitor_thread.start()

        await asyncio.sleep(1.5)

        if proc.poll() is not None:
            err_output = ""
            try:
                if proc.stderr:
                    err_output = proc.stderr.read().strip()
            except Exception:
                pass
            raise RuntimeError(f"Scrcpy terminated on startup (code {proc.returncode}): {err_output}")

        if features["has_new_display"]:
            for _ in range(8):
                await asyncio.sleep(0.5)
                resolved_id = await self.adb.get_secondary_display_id(target)
                if resolved_id is not None:
                    self.active_session["display_id"] = resolved_id
                    await self.adb.launch_home_on_display(target, resolved_id)
                    break
        elif display_id is not None:
            await self.adb.launch_home_on_display(target, display_id)

        return {
            "success": True,
            "message": "Android DeX Mode launched successfully.",
            "session": self.active_session,
        }

    async def stop_workspace(self, target: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            active_target = target or (self.active_session.get("target") if self.active_session else None)
            proc = self._scrcpy_process

            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    for _ in range(20):
                        if proc.poll() is not None:
                            break
                        time.sleep(0.1)
                    if proc.poll() is None:
                        proc.kill()
                except Exception as e:
                    log.warning(f"Error terminating scrcpy process: {e}")

            self._scrcpy_process = None
            self.active_session = None

        if active_target and self._used_overlay_devices:
            await self.adb.destroy_overlay_display(active_target)

        return {"success": True, "message": "Android DeX session destroyed."}

    async def list_applications(self) -> List[str]:
        with self._lock:
            if not self.active_session:
                return []
            target = self.active_session.get("target")

        if not target:
            return []
        return await self.adb.list_installed_packages(target)

    async def launch_application(self, package_name: str) -> Dict[str, Any]:
        with self._lock:
            if not self.active_session:
                raise RuntimeError("No active desktop workspace session.")
            target = self.active_session["target"]
            display_id = self.active_session["display_id"]

        if display_id is None:
            raise RuntimeError("Display ID not resolved yet. Please wait a moment and retry.")

        success, msg = await self.adb.launch_package_on_display(target, package_name, display_id)
        return {"success": success, "message": msg}
