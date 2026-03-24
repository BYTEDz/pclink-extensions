import pyautogui
from pclink.core.extension_base import ExtensionBase
from fastapi import APIRouter

class Extension(ExtensionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_routes()

    def setup_routes(self):
        @self.router.post("/control/{action}")
        async def control(action: str):
            """Simulates key presses for PowerPoint and other presentation software."""
            try:
                if action == "next":
                    pyautogui.press("right")
                elif action == "prev":
                    pyautogui.press("left")
                elif action == "start":
                    pyautogui.press("f5")
                elif action == "start_current":
                    pyautogui.hotkey("shift", "f5")
                elif action == "stop":
                    pyautogui.press("esc")
                elif action == "black":
                    pyautogui.press("b")
                elif action == "white":
                    pyautogui.press("w")
                elif action == "laser":
                    pyautogui.hotkey("ctrl", "l")
                return {"success": True, "action": action}
            except Exception as e:
                self.logger.error(f"Action '{action}' failed: {e}")
                return {"success": False, "error": str(e)}

    def initialize(self) -> bool:
        self.logger.info("PPT Controller Pro initialized. Ready for presentation.")
        return True

    def cleanup(self):
        pass

    def get_routes(self) -> APIRouter:
        return self.router
