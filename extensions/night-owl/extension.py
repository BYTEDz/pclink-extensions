import subprocess
import os
from fastapi import APIRouter, HTTPException, Body
from typing import Dict
from pclink.core.extension_base import ExtensionBase

class Extension(ExtensionBase):
    def __init__(self, metadata, extension_path, config: dict):
        super().__init__(metadata, extension_path, config)
        self.is_supported = False
        self.last_brightness = 50
        self.creation_flags = 0
        if os.name == 'nt':
            # 0x08000000 is CREATE_NO_WINDOW
            self.creation_flags = 0x08000000
        
        self.setup_routes()

    def _check_support(self):
        """Check if WMI Brightness is supported on this machine."""
        try:
            ps_command = "if (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness) { exit 0 } else { exit 1 }"
            result = subprocess.run(
                ["powershell", "-Command", ps_command],
                capture_output=True,
                creationflags=self.creation_flags,
                check=False
            )
            return result.returncode == 0
        except:
            return False

    def _set_brightness(self, level: int):
        if not self.is_supported: return False
        try:
            level = max(0, min(100, level))
            ps_command = f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {level})"
            subprocess.run(
                ["powershell", "-Command", ps_command],
                capture_output=True,
                creationflags=self.creation_flags,
                check=True
            )
            self.last_brightness = level
            return True
        except:
            return False

    def _get_brightness(self) -> int:
        if not self.is_supported: return self.last_brightness
        try:
            ps_command = "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness"
            result = subprocess.run(
                ["powershell", "-Command", ps_command],
                capture_output=True,
                text=True,
                creationflags=self.creation_flags,
                check=True
            )
            self.last_brightness = int(result.stdout.strip())
            return self.last_brightness
        except:
            return self.last_brightness

    def setup_routes(self):
        @self.router.get("/status")
        async def get_status():
            return {
                "supported": self.is_supported,
                "brightness": self._get_brightness()
            }

        @self.router.post("/set")
        async def set_values(data: Dict = Body(...)):
            if not self.is_supported:
                raise HTTPException(status_code=400, detail="Brightness control not supported on this PC")
            
            brightness = data.get("brightness")
            if brightness is not None:
                if self._set_brightness(int(brightness)):
                    return {"status": "success"}
                else:
                    raise HTTPException(status_code=500, detail="Failed to set brightness")
            return {"status": "no_action"}

    def initialize(self) -> bool:
        self.is_supported = self._check_support()
        if self.is_supported:
            self.logger.info("Night Owl: Hardware brightness control discovered.")
        else:
            self.logger.warning("Night Owl: WMI Brightness not supported on this hardware (Expected on Desktops).")
        return True

    def cleanup(self):
        pass

    def get_routes(self) -> APIRouter:
        return self.router
