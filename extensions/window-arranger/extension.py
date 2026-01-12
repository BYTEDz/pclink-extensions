import platform
from pclink.core.extension_base import ExtensionBase
from fastapi import APIRouter

class Extension(ExtensionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_routes()

    def setup_routes(self):
        @self.router.post("/snap/{pos}")
        async def snap(pos: str):
            if platform.system().lower() != "windows": return {"success": False, "error": "Only Windows supported"}
            try:
                import pygetwindow as gw
                win = gw.getActiveWindow()
                if not win: return {"success": False}
                if pos == "max": win.maximize()
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def initialize(self) -> bool: return True
    def cleanup(self): pass
    def get_routes(self) -> APIRouter: return self.router