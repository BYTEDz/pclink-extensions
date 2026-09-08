import asyncio
import gettext
import logging
import os
import platform
import shutil
import stat
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

log = logging.getLogger(__name__)
_ = gettext.gettext

PLATFORM_TOOLS_URLS: Dict[str, str] = {
    "windows": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
    "linux": "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
    "darwin": "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip",
}

SCRCPY_WIN64_URL = "https://github.com/Genymobile/scrcpy/releases/download/v2.4/scrcpy-win64-v2.4.zip"


class BinaryManager:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.bin_dir = self.data_dir / "bin"
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        self.os_type = platform.system().lower()

    def resolve_adb_path(self) -> Optional[str]:
        system_adb = shutil.which("adb")
        if system_adb:
            return system_adb

        candidate_name = "adb.exe" if self.os_type == "windows" else "adb"
        local_adb = self.bin_dir / candidate_name
        if local_adb.is_file():
            return str(local_adb)

        local_sub_adb = self.bin_dir / "platform-tools" / candidate_name
        if local_sub_adb.is_file():
            return str(local_sub_adb)

        return None

    def resolve_scrcpy_path(self) -> Optional[str]:
        system_scrcpy = shutil.which("scrcpy")
        if system_scrcpy:
            return system_scrcpy

        candidate_name = "scrcpy.exe" if self.os_type == "windows" else "scrcpy"
        local_scrcpy = self.bin_dir / candidate_name
        if local_scrcpy.is_file():
            return str(local_scrcpy)

        for candidate in self.bin_dir.glob("scrcpy*"):
            if candidate.is_dir():
                sub_bin = candidate / candidate_name
                if sub_bin.is_file():
                    return str(sub_bin)

        return None

    def check_binaries(self) -> Dict[str, Optional[str]]:
        return {
            "adb": self.resolve_adb_path(),
            "scrcpy": self.resolve_scrcpy_path(),
            "os": self.os_type,
            "storage_path": str(self.bin_dir),
        }

    async def ensure_binaries(
        self, progress_callback: Optional[Callable[[str, int], None]] = None
    ) -> Tuple[bool, str]:
        status = self.check_binaries()
        if status["adb"] and status["scrcpy"]:
            return True, _("Binaries installed successfully.")

        try:
            if not status["adb"]:
                if progress_callback:
                    progress_callback(_("Downloading ADB tools..."), 15)
                await self._download_platform_tools(progress_callback)

            if not status["scrcpy"]:
                if self.os_type == "windows":
                    if progress_callback:
                        progress_callback(_("Downloading scrcpy engine..."), 50)
                    await self._download_scrcpy_windows(progress_callback)
                else:
                    return False, _(
                        "Scrcpy is missing. Please install it on the host via package manager: sudo apt install scrcpy"
                    )

            if progress_callback:
                progress_callback(_("Finalizing configuration..."), 95)

            status = self.check_binaries()
            if status["adb"] and status["scrcpy"]:
                if progress_callback:
                    progress_callback(_("Setup complete."), 100)
                return True, _("Binaries installed successfully.")

            return False, _("Installation completed but binary verification failed.")

        except Exception as e:
            log.error(f"Failed to provision binaries: {e}", exc_info=True)
            return False, _("Failed to download binaries: {error}").format(error=str(e))

    async def _download_platform_tools(
        self, progress_callback: Optional[Callable[[str, int], None]]
    ) -> None:
        url = PLATFORM_TOOLS_URLS.get(self.os_type)
        if not url:
            raise RuntimeError(f"Unsupported OS platform: {self.os_type}")

        archive_path = self.bin_dir / "platform_tools.zip"
        await asyncio.to_thread(self._fetch_file, url, archive_path)

        def _extract():
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(self.bin_dir)
            if archive_path.exists():
                archive_path.unlink()

            if self.os_type != "windows":
                extracted_adb = self.bin_dir / "platform-tools" / "adb"
                if extracted_adb.exists():
                    st = os.stat(extracted_adb)
                    os.chmod(extracted_adb, st.st_mode | stat.S_IEXEC)

        await asyncio.to_thread(_extract)

    async def _download_scrcpy_windows(
        self, progress_callback: Optional[Callable[[str, int], None]]
    ) -> None:
        archive_path = self.bin_dir / "scrcpy.zip"
        await asyncio.to_thread(self._fetch_file, SCRCPY_WIN64_URL, archive_path)

        def _extract():
            with zipfile.ZipFile(archive_path, "r") as zf:
                for member in zf.infolist():
                    flat_name = Path(member.filename).name
                    if flat_name:
                        dest = self.bin_dir / flat_name
                        with zf.open(member) as src, open(dest, "wb") as dst:
                            shutil.copyfileobj(src, dst)
            if archive_path.exists():
                archive_path.unlink()

        await asyncio.to_thread(_extract)

    def _fetch_file(self, url: str, destination: Path) -> None:
        req = urllib.request.Request(
            url, headers={"User-Agent": "PCLink-DesktopWorkspace/1.0"}
        )
        with urllib.request.urlopen(req, timeout=60) as response, open(
            destination, "wb"
        ) as out_file:
            shutil.copyfileobj(response, out_file)
