import asyncio
import logging
import re
from typing import List, Optional, Tuple

log = logging.getLogger(__name__)


class AdbService:
    def __init__(self, adb_path_resolver):
        self._get_adb_path = adb_path_resolver

    async def _run_adb(
        self, args: List[str], target_device: Optional[str] = None, timeout: float = 15.0
    ) -> Tuple[int, str, str]:
        adb_bin = self._get_adb_path()
        if not adb_bin:
            raise FileNotFoundError("ADB binary could not be resolved.")

        cmd = [adb_bin]
        if target_device:
            cmd.extend(["-s", target_device])
        cmd.extend(args)

        log.debug(f"[ADB EXEC] {' '.join(cmd)}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            stdout = stdout_bytes.decode("utf-8", errors="ignore").strip()
            stderr = stderr_bytes.decode("utf-8", errors="ignore").strip()
            return process.returncode or 0, stdout, stderr
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            return -1, "", f"ADB command timed out after {timeout} seconds"

    async def connect(self, ip: str, port: int = 5555) -> Tuple[bool, str]:
        target = f"{ip}:{port}"
        code, out, err = await self._run_adb(["connect", target], timeout=10.0)
        output = out or err
        if code == 0 and ("connected to" in output.lower() or "already connected to" in output.lower()):
            return True, output
        return False, output or "Unknown connection error"

    async def pair(self, ip: str, port: int, pairing_code: str) -> Tuple[bool, str]:
        target = f"{ip}:{port}"
        code, out, err = await self._run_adb(["pair", target, pairing_code], timeout=15.0)
        output = out or err
        if code == 0 and "successfully paired" in output.lower():
            return True, output
        return False, output or "Pairing failed"

    async def disconnect(self, target: str) -> None:
        await self._run_adb(["disconnect", target])

    async def open_wireless_debugging_settings(
        self, target_device: Optional[str] = None
    ) -> Tuple[bool, str]:
        intents = [
            ["shell", "am", "start", "-a", "android.settings.WIRELESS_DEBUGGING_SETTINGS"],
            ["shell", "am", "start", "-a", "android.settings.APPLICATION_DEVELOPMENT_SETTINGS"],
        ]
        for cmd in intents:
            code, out, err = await self._run_adb(cmd, target_device=target_device)
            if code == 0 and "error" not in (out + err).lower():
                return True, "Opened Wireless Debugging settings on device."
        return False, "Failed to launch settings screen via ADB."

    async def configure_desktop_mode_flags(self, target_device: str) -> bool:
        commands = [
            ["shell", "settings", "put", "global", "force_desktop_mode_on_external_displays", "1"],
            ["shell", "settings", "put", "global", "enable_freeform_support", "1"],
            ["shell", "settings", "put", "global", "force_resizable_activities", "1"],
            ["shell", "settings", "put", "global", "enable_size_compat_mode", "0"],
            ["shell", "settings", "put", "secure", "freeform_window_management", "1"],
            ["shell", "settings", "put", "global", "development_settings_enabled", "1"],
            ["shell", "wm", "set-ignore-orientation-request", "true"],
            ["shell", "wm", "set-letterbox-style", "--isEducationEnabled", "false"],
        ]
        for cmd in commands:
            code, _, err = await self._run_adb(cmd, target_device=target_device)
            if code != 0:
                log.warning(f"Failed setting desktop flag {cmd}: {err}")
        return True

    async def create_overlay_display(
        self, target_device: str, width: int = 1920, height: int = 1080, dpi: int = 210
    ) -> bool:
        overlay_val = f"{width}x{height}/{dpi}"
        code, _, err = await self._run_adb(
            ["shell", "settings", "put", "global", "overlay_display_devices", overlay_val],
            target_device=target_device,
        )
        if code != 0:
            return False

        await asyncio.sleep(0.5)
        display_id = await self.get_secondary_display_id(target_device)
        if display_id is not None:
            display_str = str(display_id)
            orientation_cmds = [
                ["shell", "wm", "set-ignore-orientation-request", "-d", display_str, "true"],
                ["shell", "wm", "density", str(dpi), "-d", display_str],
            ]
            for o_cmd in orientation_cmds:
                await self._run_adb(o_cmd, target_device=target_device)

        return True

    async def destroy_overlay_display(self, target_device: str) -> bool:
        code, _, _ = await self._run_adb(
            ["shell", "settings", "put", "global", "overlay_display_devices", "null"],
            target_device=target_device,
        )
        return code == 0

    async def get_secondary_display_id(self, target_device: str) -> Optional[int]:
        code, out, _ = await self._run_adb(
            ["shell", "dumpsys", "display"], target_device=target_device, timeout=10.0
        )
        if code != 0 or not out:
            return None

        for match in re.finditer(r'DisplayDeviceInfo\{.*?"scrcpy".*?displayId=(\d+)', out, re.DOTALL):
            return int(match.group(1))

        for match in re.finditer(r'DisplayDeviceInfo\{.*?Overlay.*?displayId=(\d+)', out, re.DOTALL):
            return int(match.group(1))

        matches = re.findall(r"mDisplayId=(\d+)", out)
        if matches:
            candidates = [int(m) for m in matches if int(m) > 0]
            if candidates:
                return candidates[-1]

        return None

    async def launch_home_on_display(self, target_device: str, display_id: int) -> bool:
        code, out, _ = await self._run_adb(
            ["shell", "pm", "path", "com.farmerbb.taskbar"], target_device=target_device
        )
        if code == 0 and "package:" in out:
            await self._run_adb(
                ["shell", "pm", "grant", "com.farmerbb.taskbar", "android.permission.WRITE_SECURE_SETTINGS"],
                target_device=target_device,
            )
            taskbar_launchers = [
                ["shell", "am", "start", "-n", "com.farmerbb.taskbar/.activity.SecondaryHomeActivity", "--display", str(display_id)],
                ["shell", "am", "start", "-n", "com.farmerbb.taskbar/.activity.MainActivity", "--display", str(display_id)],
            ]
            for cmd in taskbar_launchers:
                c, _, _ = await self._run_adb(cmd, target_device=target_device)
                if c == 0:
                    return True

        launchers = [
            ["shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.SECONDARY_HOME", "--display", str(display_id)],
            ["shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME", "--display", str(display_id)],
            ["shell", "am", "start", "-N", "--windowingMode", "5", "--display", str(display_id), "-n", "com.android.launcher3/.SecondaryHomeActivity"],
        ]
        for cmd in launchers:
            code, _, _ = await self._run_adb(cmd, target_device=target_device)
            if code == 0:
                return True
        return False

    async def list_installed_packages(self, target_device: str) -> List[str]:
        code, out, _ = await self._run_adb(
            ["shell", "pm", "list", "packages", "-3"], target_device=target_device
        )
        if code != 0 or not out:
            return []
        packages = []
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                packages.append(line.replace("package:", "").strip())
        return sorted(packages)

    async def launch_package_on_display(
        self, target_device: str, package_name: str, display_id: int
    ) -> Tuple[bool, str]:
        code, out, _ = await self._run_adb(
            ["shell", "cmd", "package", "resolve-activity", "--brief", package_name],
            target_device=target_device,
        )
        component = None
        if code == 0 and out:
            lines = [line.strip() for line in out.splitlines() if line.strip()]
            if len(lines) >= 2 and "/" in lines[-1]:
                component = lines[-1]

        if component:
            start_cmd = [
                "shell", "am", "start",
                "-a", "android.intent.action.MAIN",
                "-c", "android.intent.category.LAUNCHER",
                "--display", str(display_id),
                "-n", component,
            ]
        else:
            start_cmd = [
                "shell", "monkey",
                "-p", package_name,
                "-c", "android.intent.category.LAUNCHER",
                "--display", str(display_id),
                "1",
            ]

        launch_code, launch_out, launch_err = await self._run_adb(start_cmd, target_device=target_device)
        success = launch_code == 0 and "error" not in (launch_out + launch_err).lower()
        return success, launch_out or launch_err
