import time
from pclink.core.extension_base import ExtensionBase
from fastapi import APIRouter
from pynput.keyboard import Key, Controller

class Extension(ExtensionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.keyboard = Controller()
        self.setup_routes()

    def _tap(self, key):
        """Simulates a key tap with a small delay for OS reliability"""
        self.keyboard.press(key)
        time.sleep(0.05) 
        self.keyboard.release(key)

    def setup_routes(self):
        @self.router.post("/control/{action}")
        async def media_control(action: str):
            key_map = {
                "play_pause": Key.media_play_pause,
                "next": Key.media_next,
                "prev": Key.media_previous,
                "vol_up": Key.media_volume_up,
                "vol_down": Key.media_volume_down,
                "mute": Key.media_volume_mute,
                # Seeking usually uses Arrow Keys on the active window
                "seek_fwd": Key.right, 
                "seek_bwd": Key.left
            }
            
            if action in key_map:
                try:
                    self._tap(key_map[action])
                    return {"success": True, "action": action}
                except Exception as e:
                    return {"success": False, "error": str(e)}
            return {"success": False, "error": "Invalid action"}

    def initialize(self) -> bool:
        self.logger.info("Media Master Pro Active")
        return True

    def cleanup(self):
        pass

    def get_routes(self) -> APIRouter:
        return self.router