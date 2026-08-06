import base64
import io
import os
import tempfile
from datetime import datetime
from pclink.core.extension_base import ExtensionBase
from fastapi import APIRouter
from fastapi.responses import Response

class Extension(ExtensionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_routes()

    def setup_routes(self):
        @self.router.post("/capture")
        async def capture():
            try:
                import mss
                with mss.mss() as sct:
                    monitor = sct.monitors[1]
                    screenshot = sct.grab(monitor)
                    img_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
                    b64 = base64.b64encode(img_bytes).decode()
                    return {"success": True, "image": b64, "width": screenshot.size[0], "height": screenshot.size[1]}
            except ImportError:
                import pyautogui
                screenshot = pyautogui.screenshot()
                buf = io.BytesIO()
                screenshot.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode()
                return {"success": True, "image": b64, "width": screenshot.width, "height": screenshot.height}

        @self.router.post("/capture-region")
        async def capture_region(data: dict):
            try:
                x, y, w, h = data["x"], data["y"], data["width"], data["height"]
                import mss
                with mss.mss() as sct:
                    monitor = {"top": y, "left": x, "width": w, "height": h}
                    screenshot = sct.grab(monitor)
                    img_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
                    b64 = base64.b64encode(img_bytes).decode()
                    return {"success": True, "image": b64}
            except ImportError:
                import pyautogui
                screenshot = pyautogui.screenshot(region=(x, y, w, h))
                buf = io.BytesIO()
                screenshot.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode()
                return {"success": True, "image": b64}

        @self.router.post("/save")
        async def save_screenshot(data: dict):
            b64 = data.get("image", "")
            folder = data.get("folder", "")
            img_bytes = base64.b64decode(b64)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            if folder and os.path.isdir(folder):
                save_dir = folder
            else:
                save_dir = os.path.join(tempfile.gettempdir(), "pclink-screenshots")
            os.makedirs(save_dir, exist_ok=True)
            path = os.path.join(save_dir, f"screenshot_{ts}.png")
            with open(path, "wb") as f:
                f.write(img_bytes)
            return {"success": True, "path": path}

    def initialize(self) -> bool:
        return True

    def cleanup(self):
        pass

    def get_routes(self) -> APIRouter:
        return self.router
