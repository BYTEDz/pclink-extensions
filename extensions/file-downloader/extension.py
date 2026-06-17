import asyncio
import os
import uuid
import time
import logging
import re
import json
from pathlib import Path
from typing import Dict, Optional
from fastapi import APIRouter, Body, HTTPException
from pclink.core.extension_base import ExtensionBase, ExtensionMetadata
from pclink.core.extension_context import ExtensionContext
import httpx

logger = logging.getLogger("pclink.downloader")

class DownloadTask:
    def __init__(self, task_id: str, url: str, filename: str, save_path: Path):
        self.id = task_id
        self.url = url
        self.filename = filename
        self.path = save_path
        self.bytes_downloaded = 0
        self.total_size = 0
        self.status = "paused"  # downloading, paused, completed, error
        self.error = None
        self.last_updated = time.time()
        
        # Speed measurement
        self.speed = 0.0  # bytes/sec
        self._last_bytes = 0
        self._last_speed_time = time.time()
        
        # Async task reference
        self._task: Optional[asyncio.Task] = None

    def update_speed(self):
        now = time.time()
        dt = now - self._last_speed_time
        if dt >= 0.5:
            bytes_diff = max(0, self.bytes_downloaded - self._last_bytes)
            self.speed = bytes_diff / dt
            self._last_bytes = self.bytes_downloaded
            self._last_speed_time = now

    def get_current_speed(self) -> float:
        now = time.time()
        dt = now - self._last_speed_time
        if dt > 2.0:
            self.speed = 0.0
            self._last_bytes = self.bytes_downloaded
            self._last_speed_time = now
        return self.speed

    def cancel(self):
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None
        if self.status == "downloading":
            self.status = "paused"

    def start(self, client: httpx.AsyncClient):
        self.cancel()
        self.status = "downloading"
        self.error = None
        self._last_bytes = self.bytes_downloaded
        self._last_speed_time = time.time()
        self._task = asyncio.create_task(self._download_loop(client))

    async def _download_loop(self, client: httpx.AsyncClient):
        try:
            headers = {}
            file_exists = self.path.exists()
            current_file_size = self.path.stat().st_size if file_exists else 0
            
            if file_exists:
                self.bytes_downloaded = current_file_size
            else:
                self.bytes_downloaded = 0

            if self.bytes_downloaded > 0:
                headers["Range"] = f"bytes={self.bytes_downloaded}-"

            async with client.stream("GET", self.url, headers=headers, follow_redirects=True) as response:
                if response.status_code == 200:
                    self.bytes_downloaded = 0
                    mode = "wb"
                elif response.status_code == 206:
                    mode = "ab"
                elif response.status_code == 416:
                    self.bytes_downloaded = 0
                    mode = "wb"
                    async with client.stream("GET", self.url, follow_redirects=True) as r2:
                        response = r2
                else:
                    response.raise_for_status()

                content_range = response.headers.get("Content-Range")
                content_length = response.headers.get("Content-Length")

                if content_range:
                    try:
                        self.total_size = int(content_range.split('/')[-1])
                    except (ValueError, IndexError):
                        pass
                elif content_length:
                    cl_val = int(content_length)
                    if response.status_code == 206:
                        self.total_size = self.bytes_downloaded + cl_val
                    else:
                        self.total_size = cl_val

                self.path.parent.mkdir(parents=True, exist_ok=True)

                with open(self.path, mode) as f:
                    async for chunk in response.aiter_bytes(chunk_size=16384):
                        f.write(chunk)
                        self.bytes_downloaded += len(chunk)
                        self.update_speed()
                        self.last_updated = time.time()
                        await asyncio.sleep(0)

                self.status = "completed"
                self.speed = 0.0

        except asyncio.CancelledError:
            self.status = "paused"
            self.speed = 0.0
            raise
        except Exception as e:
            logger.error(f"Download task {self.id} failed: {e}", exc_info=True)
            self.status = "error"
            self.error = str(e)
            self.speed = 0.0


class Extension(ExtensionBase):
    def __init__(self, metadata: ExtensionMetadata, extension_path: Path, config: Dict, context: ExtensionContext):
        super().__init__(metadata, extension_path, config, context)
        self.downloads: Dict[str, DownloadTask] = {}
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=None))
        
        # Local settings initialization
        self.settings_file = self.extension_path / "settings.json"
        self.settings = self.load_settings()
        
        self.setup_routes()

    def load_settings(self) -> Dict:
        if self.settings_file.exists():
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                self.logger.error(f"Error loading settings file: {e}")
        
        # Strict default folder detection
        return {
            "download_dir": str(Path.home() / "Downloads")
        }

    def save_settings(self):
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            self.logger.error(f"Error saving settings: {e}")

    def _get_downloads_dir(self) -> Path:
        val = self.settings.get("download_dir")
        if not val:
            val = str(Path.home() / "Downloads")
            self.settings["download_dir"] = val
            self.save_settings()
            
        downloads_dir = Path(val)
        try:
            downloads_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.warning(f"Could not create path {downloads_dir}, falling back to Home: {e}")
            downloads_dir = Path.home()
        return downloads_dir

    def _get_unique_filename(self, filename: str) -> str:
        downloads_dir = self._get_downloads_dir()
        path = downloads_dir / filename
        if not path.exists():
            active_paths = {t.path for t in self.downloads.values()}
            if path not in active_paths:
                return filename

        stem = path.stem
        suffix = path.suffix
        counter = 1
        while True:
            new_filename = f"{stem} ({counter}){suffix}"
            new_path = downloads_dir / new_filename
            if not new_path.exists() and new_path not in {t.path for t in self.downloads.values()}:
                return new_filename
            counter += 1

    def setup_routes(self):
        @self.router.get("/downloads")
        async def list_downloads():
            return {
                tid: {
                    "id": t.id,
                    "url": t.url,
                    "filename": t.filename,
                    "bytes_downloaded": t.bytes_downloaded,
                    "total_size": t.total_size,
                    "status": t.status,
                    "error": t.error,
                    "progress": min(100.0, (t.bytes_downloaded / t.total_size * 100)) if t.total_size > 0 else 0,
                    "speed": t.get_current_speed(),
                    "last_updated": t.last_updated,
                    "save_path": str(t.path)
                } for tid, t in self.downloads.items()
            }

        @self.router.get("/downloads/config")
        async def get_config():
            return {
                "download_dir": str(self._get_downloads_dir())
            }

        @self.router.post("/downloads/config")
        async def update_config(data: Dict = Body(...)):
            new_dir = data.get("download_dir")
            if not new_dir:
                raise HTTPException(status_code=400, detail="Path is required")
            
            target_path = Path(new_dir.strip())
            try:
                target_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid or unwritable directory: {str(e)}")
            
            self.settings["download_dir"] = str(target_path.resolve())
            self.save_settings()
            return {"status": "success", "download_dir": self.settings["download_dir"]}

        @self.router.post("/downloads/add")
        async def add_download(data: Dict = Body(...)):
            url = data.get("url")
            if not url:
                raise HTTPException(status_code=400, detail="URL is required")
            
            url = url.strip()
            filename = data.get("filename")
            
            if not filename:
                try:
                    async with httpx.AsyncClient(timeout=2.0) as temp_client:
                        head = await temp_client.head(url, follow_redirects=True)
                        cd = head.headers.get("Content-Disposition")
                        if cd and "filename=" in cd:
                            match = re.search(r'filename="?([^";\n]+)"?', cd)
                            if match:
                                filename = match.group(1).strip()
                        if not filename:
                            filename = head.url.path.split("/")[-1]
                except Exception:
                    pass

            if not filename:
                filename = url.split("/")[-1].split("?")[0] or "downloaded_file"

            filename = os.path.basename(filename)
            filename = self._get_unique_filename(filename)
            
            task_id = str(uuid.uuid4())
            save_path = self._get_downloads_dir() / filename
            
            task = DownloadTask(task_id, url, filename, save_path)
            self.downloads[task_id] = task
            
            task.start(self.client)
            return {"id": task_id, "status": "started", "filename": filename}

        @self.router.post("/downloads/bulk-add")
        async def bulk_add_downloads(data: Dict = Body(...)):
            urls = data.get("urls")
            if not urls or not isinstance(urls, list):
                raise HTTPException(status_code=400, detail="A list of URLs is required")
            
            added_tasks = []
            for url in urls:
                url = url.strip()
                if not url:
                    continue
                
                filename = url.split("/")[-1].split("?")[0] or "downloaded_file"
                filename = os.path.basename(filename)
                filename = self._get_unique_filename(filename)
                
                task_id = str(uuid.uuid4())
                save_path = self._get_downloads_dir() / filename
                
                task = DownloadTask(task_id, url, filename, save_path)
                self.downloads[task_id] = task
                task.start(self.client)
                added_tasks.append({"id": task_id, "filename": filename})
                
            return {"status": "bulk started", "tasks": added_tasks}

        @self.router.post("/downloads/pause/{task_id}")
        async def pause_download(task_id: str):
            if task_id not in self.downloads:
                raise HTTPException(status_code=404, detail="Task not found")
            
            self.downloads[task_id].cancel()
            return {"status": "paused"}

        @self.router.post("/downloads/resume/{task_id}")
        async def resume_download(task_id: str):
            if task_id not in self.downloads:
                raise HTTPException(status_code=404, detail="Task not found")
            
            task = self.downloads[task_id]
            if task.status == "completed":
                return {"status": "already completed"}
            
            task.start(self.client)
            return {"status": "resuming"}

        @self.router.post("/downloads/update-link/{task_id}")
        async def update_link(task_id: str, data: Dict = Body(...)):
            if task_id not in self.downloads:
                raise HTTPException(status_code=404, detail="Task not found")
            
            new_url = data.get("url")
            if not new_url:
                raise HTTPException(status_code=400, detail="New URL is required")
            
            task = self.downloads[task_id]
            was_downloading = (task.status == "downloading")
            
            task.cancel()
            task.url = new_url
            
            if was_downloading:
                task.start(self.client)
                
            return {"status": "link updated", "was_downloading": was_downloading}

        @self.router.delete("/downloads/{task_id}")
        async def delete_download(task_id: str):
            if task_id not in self.downloads:
                raise HTTPException(status_code=404, detail="Task not found")
            
            task = self.downloads[task_id]
            task.cancel()
            
            try:
                if task.path.exists():
                    task.path.unlink()
            except Exception:
                pass
                
            del self.downloads[task_id]
            return {"status": "deleted"}

        @self.router.post("/downloads/pause-all")
        async def pause_all():
            for task in self.downloads.values():
                if task.status == "downloading":
                    task.cancel()
            return {"status": "all paused"}

        @self.router.post("/downloads/resume-all")
        async def resume_all():
            for task in self.downloads.values():
                if task.status in ("paused", "error"):
                    task.start(self.client)
            return {"status": "all resumed"}

        @self.router.post("/downloads/clear-completed")
        async def clear_completed():
            completed_ids = [tid for tid, t in self.downloads.items() if t.status == "completed"]
            for tid in completed_ids:
                del self.downloads[tid]
            return {"status": "completed cleared", "count": len(completed_ids)}

    def initialize(self) -> bool:
        self.logger.info("File Downloader Extension initialized.")
        return True

    async def cleanup(self):
        self.logger.info("Cleaning up File Downloader Extension...")
        for task in self.downloads.values():
            task.cancel()
        await self.client.aclose()

    def get_routes(self) -> APIRouter:
        return self.router