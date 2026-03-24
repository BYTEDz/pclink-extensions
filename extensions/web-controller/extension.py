import pyautogui
import webbrowser
from pclink.core.extension_base import ExtensionBase
from fastapi import APIRouter

class Extension(ExtensionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_routes()

    def setup_routes(self):
        @self.router.post("/control/{action}")
        async def control(action: str):
            """Simulates browser navigation and scrolling."""
            try:
                # Basic scrolling
                if action == "scroll_down":
                    pyautogui.press("pagedown")
                elif action == "scroll_up":
                    pyautogui.press("pageup")
                elif action == "scroll_top":
                    pyautogui.press("home")
                elif action == "scroll_bottom":
                    pyautogui.press("end")
                
                # Navigation
                elif action == "back":
                    pyautogui.hotkey("alt", "left")
                elif action == "forward":
                    pyautogui.hotkey("alt", "right")
                elif action == "refresh":
                    pyautogui.press("f5")
                
                # Tab management
                elif action == "close_tab":
                    pyautogui.hotkey("ctrl", "w")
                elif action == "new_tab":
                    pyautogui.hotkey("ctrl", "t")
                elif action == "prev_tab":
                    pyautogui.hotkey("ctrl", "shift", "tab")
                elif action == "next_tab":
                    pyautogui.hotkey("ctrl", "tab")
                
                # Zooming (universal Ctrl +/-)
                elif action == "zoom_in":
                    pyautogui.hotkey("ctrl", "=")
                elif action == "zoom_out":
                    pyautogui.hotkey("ctrl", "-")
                elif action == "zoom_reset":
                    pyautogui.hotkey("ctrl", "0")
                
                return {"success": True, "action": action}
            except Exception as e:
                self.logger.error(f"Web control action '{action}' failed: {e}")
                return {"success": False, "error": str(e)}

        @self.router.post("/beam")
        async def beam(data: dict):
            url = data.get('url', '')
            if url:
                webbrowser.open(url)
                return {"success": True}
            return {"success": False, "error": "No URL provided"}

    def initialize(self) -> bool:
        self.logger.info("Web Navigator initialized. Ready to surf.")
        return True

    def cleanup(self):
        pass

    def get_routes(self) -> APIRouter:
        return self.router
