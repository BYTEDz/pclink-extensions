import os
import subprocess
import platform
import psutil
from pclink.core.extension_base import ExtensionBase
from fastapi import APIRouter

class Extension(ExtensionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_routes()

    def get_active_plan(self):
        sys_type = platform.system().lower()
        try:
            if sys_type == "windows":
                result = subprocess.check_output(["powercfg", "/getactivescheme"], text=True)
                if "a1841308" in result: return "saver"
                if "381b4222" in result: return "balanced"
                if "8c35e1ed" in result: return "high"
            elif sys_type == "linux":
                # Check for power-profiles-daemon
                result = subprocess.check_output(["powerprofilesctl", "get"], text=True).strip()
                mapping = {"power-saver": "saver", "balanced": "balanced", "performance": "high"}
                return mapping.get(result, "balanced")
        except:
            return "balanced"
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
                "active_plan": self.get_active_plan()
            }

        @self.router.post("/set-plan/{plan_type}")
        async def set_power_plan(plan_type: str):
            sys_type = platform.system().lower()
            try:
                if sys_type == "windows":
                    plans = {
                        "saver": "a1841308-3541-4fab-bc81-f71556f20b4a",
                        "balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
                        "high": "8c35e1ed-3df2-4814-93f6-dc3505616b61"
                    }
                    subprocess.run(["powercfg", "/setactive", plans[plan_type]], check=True)
                elif sys_type == "linux":
                    plans = {"saver": "power-saver", "balanced": "balanced", "high": "performance"}
                    subprocess.run(["powerprofilesctl", "set", plans[plan_type]], check=True)
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def initialize(self) -> bool:
        return True

    def cleanup(self):
        pass

    def get_routes(self) -> APIRouter:
        return self.router