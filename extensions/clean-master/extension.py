import os
import shutil
import platform
from pathlib import Path
from fastapi import APIRouter
from pclink.core.extension_base import ExtensionBase

class Extension(ExtensionBase):
    def __init__(self, metadata, extension_path, config: dict):
        super().__init__(metadata, extension_path, config)
        self.setup_routes()

    def _get_temp_paths(self):
        paths = []
        if platform.system() == "Windows":
            paths.append(Path(os.environ.get("TEMP", "")))
            paths.append(Path(os.environ.get("SystemRoot", "C:\\Windows")) / "Temp")
        else:
            paths.append(Path("/tmp"))
            paths.append(Path("/var/tmp"))
        return [p for p in paths if p.exists()]

    def _calculate_size(self, path):
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp):
                        total_size += os.path.getsize(fp)
        except:
            pass
        return total_size

    def _clean_path(self, path):
        deleted_size = 0
        for item in path.iterdir():
            try:
                item_size = self._calculate_size(item) if item.is_dir() else item.stat().st_size
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
                deleted_size += item_size
            except:
                pass
        return deleted_size

    def setup_routes(self):
        @self.router.get("/scan")
        async def scan():
            paths = self._get_temp_paths()
            total_bytes = sum(self._calculate_size(p) for p in paths)
            return {
                "size_mb": round(total_bytes / (1024 * 1024), 2),
                "path_count": len(paths)
            }

        @self.router.post("/clean")
        async def clean():
            paths = self._get_temp_paths()
            total_deleted = sum(self._clean_path(p) for p in paths)
            return {
                "status": "success",
                "deleted_mb": round(total_deleted / (1024 * 1024), 2)
            }

    def initialize(self) -> bool:
        self.logger.info("Clean Master Extension initialized.")
        return True

    def cleanup(self):
        pass

    def get_routes(self) -> APIRouter:
        return self.router
