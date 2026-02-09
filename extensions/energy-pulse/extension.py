import subprocess
import platform
import psutil
from pclink.core.extension_base import ExtensionBase
from fastapi import APIRouter

class Extension(ExtensionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_linux = platform.system().lower() == "linux"
        self._is_compatible = None
        self.setup_routes()

    def check_compatibility(self) -> bool:
        """Checks if the system has the required tools installed."""
        if self._is_compatible is not None:
            return self._is_compatible

        if not self.is_linux:
            self._is_compatible = False
            return False

        try:
            # Check for power-profiles-daemon
            subprocess.run(["which", "powerprofilesctl"], check=True, 
                         capture_output=True)
            self._is_compatible = True
        except:
            self._is_compatible = False
        
        return self._is_compatible

    def get_active_plan(self):
        if not self.check_compatibility():
            return "balanced"

        try:
            result = subprocess.check_output(["powerprofilesctl", "get"], 
                                           text=True, 
                                           stderr=subprocess.DEVNULL).strip()
            mapping = {"power-saver": "saver", "balanced": "balanced", "performance": "high"}
            return mapping.get(result, "balanced")
        except:
            return "balanced"

    def setup_routes(self):
        @self.router.get("/status")
        async def get_status():
            battery = psutil.sensors_battery()
            # If battery is None, it's a Desktop/AC-only machine
            return {
                "has_battery": battery is not None,
                "percent": battery.percent if battery else 100,
                "power_plugged": battery.power_plugged if battery else True,
                "active_plan": self.get_active_plan(),
                "compatible": self.check_compatibility(),
                "platform": platform.system().lower()
            }

        @self.router.post("/set-plan/{plan_type}")
        async def set_power_plan(plan_type: str):
            if not self.check_compatibility():
                return {"success": False, "error": "System not compatible"}

            try:
                plans = {"saver": "power-saver", "balanced": "balanced", "high": "performance"}
                subprocess.run(["powerprofilesctl", "set", plans[plan_type]], check=True)
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def initialize(self) -> bool:
        return self.check_compatibility()

    def cleanup(self):
        pass

    def get_routes(self) -> APIRouter:
        return self.router