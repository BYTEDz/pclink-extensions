# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 AZHAR ZOUHIR / BYTEDz

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter, Body, HTTPException

from pclink.core.extension_base import ExtensionBase, ExtensionMetadata
from pclink.core.extension_context import ExtensionContext

log = logging.getLogger(__name__)

CHUNK_SIZE = 65536
MAX_RETRIES = 3
RETRY_DELAY_SEC = 2.0

def _resolve_system_downloads_dir() -> Path:
    """Resolves the localized system standard Downloads directory across Windows, Linux, and macOS."""
    if sys.platform == "win32":
        try:
            import winreg

            sub_key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
                val, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
                expanded = os.path.expandvars(val)
                p = Path(expanded)
                if p.exists() or p.parent.exists():
                    p.mkdir(parents=True, exist_ok=True)
                    return p
        except Exception:
            pass

    elif sys.platform.startswith("linux"):
        xdg_config = Path.home() / ".config" / "user-dirs.dirs"
        if xdg_config.exists():
            try:
                for line in xdg_config.read_text(encoding="utf-8").splitlines():
                    if line.startswith("XDG_DOWNLOAD_DIR"):
                        raw = line.split("=", 1)[1].strip().strip('"')
                        raw = raw.replace("$HOME", str(Path.home()))
                        p = Path(raw)
                        if p.exists() or p.parent.exists():
                            p.mkdir(parents=True, exist_ok=True)
                            return p
            except Exception:
                pass

    fallback = Path.home() / "Downloads"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
    except Exception:
        return Path.home()

class DownloadTask:
    def __init__(
        self,
        task_id: str,
        url: str,
        filename: str,
        save_path: Path,
        total_size: int = 0,
        bytes_downloaded: int = 0,
        status: str = "paused",
    ):
        self.id = task_id
        self.url = url
        self.filename = filename
        self.path = save_path
        self.total_size = total_size
        self.bytes_downloaded = bytes_downloaded
        self.status = status
        self.error: Optional[str] = None
        self.created_at = time.time()
        self.last_updated = time.time()

        self.speed: float = 0.0
        self._speed_samples = deque(maxlen=6)
        self._last_sample_bytes = bytes_downloaded
        self._last_sample_time = time.time()

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def to_dict(self) -> Dict[str, Any]:
        progress = (
            min(100.0, (self.bytes_downloaded / self.total_size * 100))
            if self.total_size > 0
            else 0.0
        )
        return {
            "id": self.id,
            "url": self.url,
            "filename": self.filename,
            "bytes_downloaded": self.bytes_downloaded,
            "total_size": self.total_size,
            "status": self.status,
            "error": self.error,
            "progress": round(progress, 1),
            "speed": round(self.get_current_speed(), 1),
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "save_path": str(self.path),
        }

    def get_current_speed(self) -> float:
        if self.status != "downloading" or (time.time() - self._last_sample_time > 3.0):
            self.speed = 0.0
        return self.speed

    def _sample_speed(self) -> None:
        now = time.time()
        dt = now - self._last_sample_time
        if dt >= 0.5:
            delta_bytes = max(0, self.bytes_downloaded - self._last_sample_bytes)
            instant_speed = delta_bytes / dt
            self._speed_samples.append(instant_speed)
            self.speed = sum(self._speed_samples) / len(self._speed_samples)
            self._last_sample_bytes = self.bytes_downloaded
            self._last_sample_time = now

    def cancel(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None
        if self.status == "downloading":
            self.status = "paused"
        self.speed = 0.0

    def start(self, on_complete_callback=None) -> None:
        self.cancel()
        self._stop_event.clear()
        self.status = "downloading"
        self.error = None
        self._last_sample_bytes = self.bytes_downloaded
        self._last_sample_time = time.time()

        self._thread = threading.Thread(
            target=self._worker_thread,
            args=(on_complete_callback,),
            name=f"dl-worker-{self.id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def _worker_thread(self, on_complete_callback) -> None:
        retries = 0

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
        }

        while retries < MAX_RETRIES and not self._stop_event.is_set():
            try:
                if self.path.exists():
                    self.bytes_downloaded = self.path.stat().st_size
                else:
                    self.bytes_downloaded = 0

                req_headers = headers.copy()
                if self.bytes_downloaded > 0:
                    req_headers["Range"] = f"bytes={self.bytes_downloaded}-"

                with requests.get(
                    self.url,
                    headers=req_headers,
                    stream=True,
                    timeout=25.0,
                    verify=False,
                    allow_redirects=True,
                ) as resp:
                    code = resp.status_code

                    cd = resp.headers.get("Content-Disposition", "")
                    if "filename=" in cd:
                        match = re.search(r'filename=["\']?([^"\';\n]+)["\']?', cd)
                        if match:
                            server_fname = urllib.parse.unquote(match.group(1).strip())
                            if server_fname and server_fname != self.filename:
                                new_path = self.path.parent / server_fname
                                if not new_path.exists():
                                    if self.path.exists():
                                        self.path.rename(new_path)
                                    self.path = new_path
                                    self.filename = server_fname

                    content_range = resp.headers.get("Content-Range")
                    content_length = resp.headers.get("Content-Length")

                    if code == 200:
                        mode = "wb"
                        self.bytes_downloaded = 0
                        if content_length:
                            self.total_size = int(content_length)
                    elif code == 206:
                        mode = "ab"
                        if content_range:
                            match = re.search(r"/(\d+)$", content_range)
                            if match:
                                self.total_size = int(match.group(1))
                        elif content_length:
                            self.total_size = self.bytes_downloaded + int(content_length)
                    elif code == 416:
                        self.status = "completed"
                        self.speed = 0.0
                        if on_complete_callback:
                            on_complete_callback(self, None)
                        return
                    else:
                        resp.raise_for_status()

                    self.path.parent.mkdir(parents=True, exist_ok=True)

                    with open(self.path, mode) as f:
                        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                            if self._stop_event.is_set():
                                break
                            if chunk:
                                f.write(chunk)
                                self.bytes_downloaded += len(chunk)
                                self._sample_speed()
                                self.last_updated = time.time()

                    if self._stop_event.is_set():
                        self.status = "paused"
                        self.speed = 0.0
                        return

                    self.status = "completed"
                    self.speed = 0.0
                    self.last_updated = time.time()
                    if on_complete_callback:
                        on_complete_callback(self, None)
                    return

            except Exception as e:
                retries += 1
                error_str = str(e)
                log.warning(f"Download stream error '{self.filename}' (attempt {retries}/{MAX_RETRIES}): {error_str}")
                if retries >= MAX_RETRIES or self._stop_event.is_set():
                    self.status = "error"
                    self.error = error_str
                    self.speed = 0.0
                    if on_complete_callback:
                        on_complete_callback(self, error_str)
                    return
                time.sleep(RETRY_DELAY_SEC)


class Extension(ExtensionBase):
    def __init__(
        self,
        metadata: ExtensionMetadata,
        extension_path: Path,
        config: Dict[str, Any],
        context: ExtensionContext,
    ):
        super().__init__(metadata, extension_path, config, context)
        self.downloads: Dict[str, DownloadTask] = {}
        self.state_file = self.context.data_path / "tasks_state.json"
        self.config_file = self.context.data_path / "config.json"
        self._setup_routes()

    def _get_downloads_dir(self) -> Path:
        """Returns configured download directory or resolves the system standard Downloads directory."""
        if self.config_file.exists():
            try:
                cfg = json.loads(self.config_file.read_text(encoding="utf-8"))
                custom_dir = cfg.get("download_dir")
                if custom_dir:
                    p = Path(custom_dir).expanduser().resolve()
                    p.mkdir(parents=True, exist_ok=True)
                    return p
            except Exception:
                pass

        return _resolve_system_downloads_dir()

    def _persist_state(self) -> None:
        try:
            serialized = {}
            for tid, t in self.downloads.items():
                serialized[tid] = {
                    "id": t.id,
                    "url": t.url,
                    "filename": t.filename,
                    "save_path": str(t.path),
                    "total_size": t.total_size,
                    "bytes_downloaded": t.bytes_downloaded,
                    "status": "paused" if t.status == "downloading" else t.status,
                }
            self.state_file.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
        except Exception as e:
            log.error(f"Failed persisting download state: {e}")

    def _restore_persisted_tasks(self) -> None:
        if not self.state_file.exists():
            return
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
            for tid, data in raw.items():
                save_p = Path(data["save_path"])
                task = DownloadTask(
                    task_id=tid,
                    url=data["url"],
                    filename=data["filename"],
                    save_path=save_p,
                    total_size=data.get("total_size", 0),
                    bytes_downloaded=data.get("bytes_downloaded", 0),
                    status=data.get("status", "paused"),
                )
                self.downloads[tid] = task
        except Exception as e:
            log.error(f"Failed restoring download tasks: {e}")

    def _on_task_finished(self, task: DownloadTask, error: Optional[str]) -> None:
        self._persist_state()
        if not error and task.status == "completed":
            self.context.notify(
                title="Download Complete",
                message=f"Saved: {task.filename}",
                type="success",
            )
        elif error:
            self.context.notify(
                title="Download Failed",
                message=f"{task.filename}: {error}",
                type="error",
            )

    def _get_unique_filename(self, filename: str) -> str:
        d_dir = self._get_downloads_dir()
        target = d_dir / filename
        active_paths = {t.path for t in self.downloads.values()}
        if not target.exists() and target not in active_paths:
            return filename

        stem = target.stem
        suffix = target.suffix
        counter = 1
        while True:
            candidate_name = f"{stem} ({counter}){suffix}"
            candidate_path = d_dir / candidate_name
            if not candidate_path.exists() and candidate_path not in active_paths:
                return candidate_name
            counter += 1

    def _extract_filename(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        path_name = os.path.basename(parsed.path)
        if path_name and "." in path_name:
            return urllib.parse.unquote(path_name)
        return f"download_{int(time.time())}.bin"

    def _setup_routes(self):
        @self.router.get("/downloads")
        async def list_downloads():
            return {tid: t.to_dict() for tid, t in self.downloads.items()}

        @self.router.get("/downloads/config")
        async def get_config():
            return {"download_dir": str(self._get_downloads_dir())}

        @self.router.post("/downloads/config")
        async def set_config(data: Dict[str, Any] = Body(...)):
            new_dir = data.get("download_dir", "").strip()
            if not new_dir:
                raise HTTPException(status_code=400, detail="Directory path is required")

            target_path = Path(new_dir).expanduser().resolve()
            try:
                target_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid or unwritable directory: {e}")

            cfg_data = {"download_dir": str(target_path)}
            self.config_file.write_text(json.dumps(cfg_data, indent=2), encoding="utf-8")
            return {"status": "success", "download_dir": str(target_path)}

        @self.router.post("/downloads/add")
        async def add_download(data: Dict[str, Any] = Body(...)):
            url = data.get("url", "").strip()
            if not url:
                raise HTTPException(status_code=400, detail="URL is required")

            filename = data.get("filename") or self._extract_filename(url)
            safe_name = self._get_unique_filename(filename)
            task_id = str(uuid.uuid4())
            save_path = self._get_downloads_dir() / safe_name

            task = DownloadTask(task_id, url, safe_name, save_path)
            self.downloads[task_id] = task
            self._persist_state()

            task.start(self._on_task_finished)
            return {"id": task_id, "status": "started", "filename": safe_name}

        @self.router.post("/downloads/pause/{task_id}")
        async def pause_task(task_id: str):
            if task_id not in self.downloads:
                raise HTTPException(status_code=404, detail="Task not found")
            self.downloads[task_id].cancel()
            self._persist_state()
            return {"status": "paused"}

        @self.router.post("/downloads/resume/{task_id}")
        async def resume_task(task_id: str):
            if task_id not in self.downloads:
                raise HTTPException(status_code=404, detail="Task not found")
            t = self.downloads[task_id]
            if t.status != "completed":
                t.start(self._on_task_finished)
                self._persist_state()
            return {"status": "resumed"}

        @self.router.delete("/downloads/{task_id}")
        async def delete_task(task_id: str):
            if task_id not in self.downloads:
                raise HTTPException(status_code=404, detail="Task not found")
            t = self.downloads.pop(task_id)
            t.cancel()
            try:
                if t.path.exists():
                    t.path.unlink()
            except Exception:
                pass
            self._persist_state()
            return {"status": "deleted"}

        @self.router.post("/downloads/open-location/{task_id}")
        async def open_location(task_id: str):
            if task_id not in self.downloads:
                raise HTTPException(status_code=404, detail="Task not found")
            target = self.downloads[task_id].path.parent
            if sys.platform == "win32":
                await asyncio.to_thread(os.startfile, str(target))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)], start_new_session=True)
            return {"status": "opened", "path": str(target)}

        @self.router.post("/downloads/pause-all")
        async def pause_all():
            for t in self.downloads.values():
                if t.status == "downloading":
                    t.cancel()
            self._persist_state()
            return {"status": "all paused"}

        @self.router.post("/downloads/resume-all")
        async def resume_all():
            for t in self.downloads.values():
                if t.status in ("paused", "error"):
                    t.start(self._on_task_finished)
            self._persist_state()
            return {"status": "all resumed"}

        @self.router.post("/downloads/clear-completed")
        async def clear_completed():
            done = [tid for tid, t in self.downloads.items() if t.status == "completed"]
            for tid in done:
                del self.downloads[tid]
            self._persist_state()
            return {"status": "cleared", "count": len(done)}

    def initialize(self) -> bool:
        self._restore_persisted_tasks()
        self.logger.info("File Downloader Pro v2.1 initialized.")
        return True

    def cleanup(self):
        self._persist_state()
        for t in self.downloads.values():
            t.cancel()

    def get_routes(self) -> APIRouter:
        return self.router