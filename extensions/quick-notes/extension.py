import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Body
from typing import List, Dict

from pclink.core.extension_base import ExtensionBase

class Extension(ExtensionBase):
    def __init__(self, metadata, extension_path, config: dict):
        super().__init__(metadata, extension_path, config)
        self.notes_file = self.extension_path / "notes.json"
        self.setup_routes()

    def setup_routes(self):
        @self.router.get("/data")
        async def get_notes():
            return self._load_notes()

        @self.router.post("/save")
        async def save_notes(notes: List[Dict] = Body(...)):
            self._save_notes(notes)
            return {"status": "success"}

    def _load_notes(self) -> List[Dict]:
        if not self.notes_file.exists():
            return [{"id": 1, "content": "Welcome to Quick Notes!", "color": "#f39c12"}]
        try:
            with open(self.notes_file, "r") as f:
                return json.load(f)
        except:
            return []

    def _save_notes(self, notes: List[Dict]):
        with open(self.notes_file, "w") as f:
            json.dump(notes, f)

    def initialize(self) -> bool:
        self.logger.info("Quick Notes Extension initialized.")
        return True

    def cleanup(self):
        self.logger.info("Quick Notes Extension shutting down.")

    def get_routes(self) -> APIRouter:
        return self.router
