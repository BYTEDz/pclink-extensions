# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 AZHAR ZOUHIR / BYTEDz

import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter

from pclink.core.extension_base import ExtensionBase, ExtensionMetadata
from pclink.core.extension_context import ExtensionContext

log = logging.getLogger(__name__)

class Extension(ExtensionBase):
    def __init__(
        self,
        metadata: ExtensionMetadata,
        extension_path: Path,
        config: Dict[str, Any],
        context: ExtensionContext,
    ):
        super().__init__(metadata, extension_path, config, context)
        self.setup_routes()

    def setup_routes(self):
        @self.router.get("/status")
        async def get_status():
            return {
                "status": "running",
                "extension": self.metadata.name,
                "version": self.metadata.version,
            }

    def initialize(self) -> bool:
        self.logger.info(f"{self.metadata.name} v{self.metadata.version} initialized.")
        return True

    def cleanup(self):
        self.logger.info(f"{self.metadata.name} shutting down.")

    def get_routes(self) -> APIRouter:
        return self.router