import webbrowser
from pclink.core.extension_base import ExtensionBase
from fastapi import APIRouter

class Extension(ExtensionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_routes()

    def setup_routes(self):
        @self.router.post("/beam")
        async def beam(data: dict):
            webbrowser.open(data['url'])
            return {"success": True}

    def initialize(self) -> bool: return True
    def cleanup(self): pass
    def get_routes(self) -> APIRouter: return self.router