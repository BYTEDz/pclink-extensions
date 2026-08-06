import time
from pclink.core.extension_base import ExtensionBase
from fastapi import APIRouter
from pynput.keyboard import Key, Controller

class Extension(ExtensionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.keyboard = Controller()
        self.setup_routes()

    def setup_routes(self):
        @self.router.post("/type")
        async def type_text(data: dict):
            text = data.get("text", "")
            for char in text:
                if char == "\n":
                    self.keyboard.press(Key.enter)
                    self.keyboard.release(Key.enter)
                else:
                    self.keyboard.press(char)
                    self.keyboard.release(char)
                time.sleep(0.005)
            return {"success": True, "chars": len(text)}

        @self.router.post("/hotkey")
        async def send_hotkey(data: dict):
            combo = data.get("keys", [])
            for key in combo:
                k = getattr(Key, key, key)
                self.keyboard.press(k)
            for key in reversed(combo):
                k = getattr(Key, key, key)
                self.keyboard.release(k)
            return {"success": True, "combo": combo}

    def initialize(self) -> bool:
        return True

    def cleanup(self):
        pass

    def get_routes(self) -> APIRouter:
        return self.router
