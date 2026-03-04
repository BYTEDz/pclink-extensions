from fastapi import APIRouter
from pathlib import Path
from typing import Dict
from pclink.core.extension_base import ExtensionBase, ExtensionMetadata
from pclink.core.extension_context import ExtensionContext

class Extension(ExtensionBase):
    def __init__(self, metadata: ExtensionMetadata, extension_path: Path, config: Dict, context: ExtensionContext):
        super().__init__(metadata, extension_path, config, context)
        self.setup_routes()

    def setup_routes(self):
        @self.router.get("/info")
        async def get_info():
            return {
                "status": "active",
                "capabilities": [
                    "fullscreen",
                    "rotation",
                    "keyboard",
                    "mouse_overlay"
                ],
                "platform": self.context.platform
            }

    def initialize(self) -> bool:
        self.logger.info("Capabilities Demo active.")
        return True

    def cleanup(self):
        self.logger.info("Capabilities Demo shutting down.")

    def get_routes(self) -> APIRouter:
        return self.router
