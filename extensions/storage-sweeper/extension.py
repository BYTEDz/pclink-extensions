# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 AZHAR ZOUHIR / BYTEDz

import asyncio
import logging
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, HTTPException

from pclink.core.extension_base import ExtensionBase, ExtensionMetadata

log = logging.getLogger(__name__)


class Extension(ExtensionBase):
    def __init__(
        self,
        metadata: ExtensionMetadata,
        extension_path: Path,
        config: Dict[str, Any],
        context=None,
    ):
        super().__init__(metadata, extension_path, config, context)
        self._setup_routes()

    def _get_target_paths(self) -> List[Path]:
        paths = []
        if sys.platform == "win32":
            temp_env = os.environ.get("TEMP") or os.environ.get("TMP")
            if temp_env:
                paths.append(Path(temp_env))
            win_temp = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "Temp"
            if win_temp.exists():
                paths.append(win_temp)
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                local_temp = Path(local_app_data) / "Temp"
                if local_temp.exists() and local_temp not in paths:
                    paths.append(local_temp)
        else:
            paths.append(Path("/tmp"))
            paths.append(Path("/var/tmp"))
            user_cache = Path.home() / ".cache"
            if user_cache.exists():
                paths.append(user_cache)

        return [p for p in paths if p.exists() and p.is_dir()]

    def _calculate_path_size(self, path: Path) -> Tuple[int, int]:
        total_bytes = 0
        file_count = 0
        try:
            for root, _, files in os.walk(str(path)):
                for f in files:
                    fp = os.path.join(root, f)
                    if not os.path.islink(fp):
                        try:
                            total_bytes += os.path.getsize(fp)
                            file_count += 1
                        except (OSError, PermissionError):
                            continue
        except (OSError, PermissionError):
            pass
        return total_bytes, file_count

    def _clean_single_path(self, path: Path) -> Tuple[int, int]:
        deleted_bytes = 0
        deleted_count = 0
        try:
            for item in path.iterdir():
                try:
                    if item.is_file() or item.is_symlink():
                        size = item.stat().st_size
                        item.unlink()
                        deleted_bytes += size
                        deleted_count += 1
                    elif item.is_dir():
                        size, count = self._calculate_path_size(item)
                        shutil.rmtree(item, ignore_errors=True)
                        deleted_bytes += size
                        deleted_count += count
                except (PermissionError, OSError):
                    # Locked or in-use system files are skipped safely
                    continue
        except (PermissionError, OSError):
            pass
        return deleted_bytes, deleted_count

    def _setup_routes(self):
        @self.router.get("/scan")
        async def scan_junk():
            def do_scan():
                paths = self._get_target_paths()
                total_bytes = 0
                total_files = 0
                for p in paths:
                    b, c = self._calculate_path_size(p)
                    total_bytes += b
                    total_files += c
                return {
                    "size_mb": round(total_bytes / (1024 * 1024), 2),
                    "file_count": total_files,
                    "path_count": len(paths),
                }

            return await asyncio.to_thread(do_scan)

        @self.router.post("/clean")
        async def clean_junk():
            def do_clean():
                paths = self._get_target_paths()
                total_freed = 0
                total_deleted = 0
                for p in paths:
                    b, c = self._clean_single_path(p)
                    total_freed += b
                    total_deleted += c
                return {
                    "status": "success",
                    "deleted_mb": round(total_freed / (1024 * 1024), 2),
                    "deleted_count": total_deleted,
                }

            return await asyncio.to_thread(do_clean)

    def initialize(self) -> bool:
        self.logger.info("Storage Sweeper v2 worker initialized.")
        return True

    def cleanup(self):
        self.logger.info("Storage Sweeper v2 shutting down.")

    def get_routes(self) -> APIRouter:
        return self.router
