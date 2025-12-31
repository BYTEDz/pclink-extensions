from fastapi import APIRouter
from pathlib import Path
from typing import Dict
from pclink.core.extension_base import ExtensionBase, ExtensionMetadata
from pclink.core.extension_context import ExtensionContext

class Extension(ExtensionBase):
    def __init__(self, metadata: ExtensionMetadata, extension_path: Path, config: Dict, context: ExtensionContext):
        super().__init__(metadata, extension_path, config, context)
        # Initialize your router and components here
        self.setup_routes()

    def setup_routes(self):
        """Define your API endpoints here."""
        @self.router.get("/status")
        async def get_status():
            return {
                "status": "running",
                "extension": self.metadata.display_name,
                "platform": self.context.platform
            }

    def initialize(self) -> bool:
        """Called by PCLink when the extension is loaded."""
        self.logger.info(f"{self.metadata.display_name} has been initialized.")
        return True

    def cleanup(self):
        """Called when PCLink shuts down or the extension is disabled."""
        self.logger.info(f"{self.metadata.display_name} is cleaning up...")

    def get_routes(self) -> APIRouter:
        """Return the router to be mounted by the server."""
        return self.router
