# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 AZHAR ZOUHIR / BYTEDz

import asyncio
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException

from pclink.core.extension_base import ExtensionBase, ExtensionMetadata
from pclink.core.extension_context import ExtensionContext

log = logging.getLogger(__name__)

OS_NAME = platform.system().lower()
if OS_NAME == "windows":
    import ctypes
    from ctypes import wintypes


class SafeClipboard:
    """Non-blocking, fail-safe clipboard manager with strict execution timeouts."""

    def __init__(self):
        self.os_name = OS_NAME
        self.copy_cmd: Optional[List[str]] = None
        self.paste_cmd: Optional[List[str]] = None

        if self.os_name == "windows":
            self._init_windows()
        elif self.os_name == "linux":
            self._init_linux()
        elif self.os_name == "darwin":
            self._init_mac()

    def _init_windows(self):
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        self.CF_UNICODETEXT = 13
        self.GMEM_MOVEABLE = 0x0002

        self.user32.OpenClipboard.argtypes = [wintypes.HWND]
        self.user32.OpenClipboard.restype = wintypes.BOOL
        self.user32.CloseClipboard.argtypes = []
        self.user32.CloseClipboard.restype = wintypes.BOOL
        self.user32.GetClipboardData.argtypes = [wintypes.UINT]
        self.user32.GetClipboardData.restype = wintypes.HANDLE
        self.user32.EmptyClipboard.argtypes = []
        self.user32.EmptyClipboard.restype = wintypes.BOOL
        self.user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        self.user32.SetClipboardData.restype = wintypes.HANDLE

        self.kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        self.kernel32.GlobalLock.restype = wintypes.LPVOID
        self.kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        self.kernel32.GlobalUnlock.restype = wintypes.BOOL
        self.kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        self.kernel32.GlobalAlloc.restype = wintypes.HGLOBAL

    def _init_linux(self):
        if shutil.which("wl-paste") and shutil.which("wl-copy"):
            self.copy_cmd = ["wl-copy"]
            self.paste_cmd = ["wl-paste", "-n"]
        elif shutil.which("xclip"):
            self.copy_cmd = ["xclip", "-selection", "clipboard"]
            self.paste_cmd = ["xclip", "-selection", "clipboard", "-o"]
        elif shutil.which("xsel"):
            self.copy_cmd = ["xsel", "-b", "-i"]
            self.paste_cmd = ["xsel", "-b", "-o"]

    def _init_mac(self):
        if shutil.which("pbcopy") and shutil.which("pbpaste"):
            self.copy_cmd = ["pbcopy"]
            self.paste_cmd = ["pbpaste"]

    def get_text(self) -> Optional[str]:
        if self.os_name == "windows":
            # Guard against lockups by capping open attempts with short intervals
            for _ in range(3):
                try:
                    if self.user32.OpenClipboard(None):
                        try:
                            h_data = self.user32.GetClipboardData(self.CF_UNICODETEXT)
                            if h_data:
                                p_data = self.kernel32.GlobalLock(h_data)
                                if p_data:
                                    text = ctypes.c_wchar_p(p_data).value
                                    self.kernel32.GlobalUnlock(h_data)
                                    return text
                        finally:
                            self.user32.CloseClipboard()
                        return None
                except Exception:
                    pass
                time.sleep(0.04)
            return None

        elif self.paste_cmd:
            try:
                res = subprocess.run(
                    self.paste_cmd,
                    capture_output=True,
                    timeout=1.5,
                )
                if res.returncode == 0:
                    return res.stdout.decode("utf-8", errors="ignore")
            except (subprocess.TimeoutExpired, Exception):
                pass
        return None

    def set_text(self, text: str) -> bool:
        if self.os_name == "windows":
            for _ in range(3):
                try:
                    if self.user32.OpenClipboard(None):
                        try:
                            self.user32.EmptyClipboard()
                            count = len(text) + 1
                            byte_count = count * ctypes.sizeof(ctypes.c_wchar)
                            h_mem = self.kernel32.GlobalAlloc(self.GMEM_MOVEABLE, byte_count)
                            if h_mem:
                                p_mem = self.kernel32.GlobalLock(h_mem)
                                if p_mem:
                                    ctypes.memmove(p_mem, text, byte_count)
                                    self.kernel32.GlobalUnlock(h_mem)
                                    self.user32.SetClipboardData(self.CF_UNICODETEXT, h_mem)
                                    return True
                        finally:
                            self.user32.CloseClipboard()
                        return False
                except Exception:
                    pass
                time.sleep(0.04)
            return False

        elif self.copy_cmd:
            try:
                subprocess.run(
                    self.copy_cmd,
                    input=text.encode("utf-8"),
                    check=True,
                    timeout=1.5,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except (subprocess.TimeoutExpired, Exception):
                return False
        return False


class Extension(ExtensionBase):
    def __init__(
        self,
        metadata: ExtensionMetadata,
        extension_path: Path,
        config: Dict[str, Any],
        context: ExtensionContext,
    ):
        super().__init__(metadata, extension_path, config, context)
        self.clipboard = SafeClipboard()
        self.history_file = self.context.data_path / "history.json"

        self.history: List[Dict[str, Any]] = []
        self._load_history()

        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        self._save_debounce_timer: Optional[threading.Timer] = None

        self._setup_routes()

    def _load_history(self):
        if not self.history_file.exists():
            return
        try:
            raw = json.loads(self.history_file.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                self.history = raw[:50]
        except Exception as e:
            self.logger.warning(f"Could not load clipboard history file: {e}")

    def _persist_history_debounced(self):
        if self._save_debounce_timer:
            self._save_debounce_timer.cancel()

        def do_save():
            try:
                self.history_file.write_text(
                    json.dumps(self.history, indent=2), encoding="utf-8"
                )
            except Exception as e:
                self.logger.error(f"Error saving history file: {e}")

        self._save_debounce_timer = threading.Timer(0.5, do_save)
        self._save_debounce_timer.start()

    def _add_to_history(self, content: str):
        clean_text = content.strip()
        if not clean_text:
            return

        if self.history and self.history[0].get("content") == clean_text:
            return

        entry = {
            "id": int(time.time() * 1000),
            "content": clean_text,
            "timestamp": time.time(),
            "type": "text",
        }

        self.history.insert(0, entry)
        if len(self.history) > 50:
            self.history = self.history[:50]

        self._persist_history_debounced()

    def _monitor_loop(self):
        last_text = self.clipboard.get_text()

        while not self._stop_event.is_set():
            try:
                current_text = self.clipboard.get_text()
                if current_text and current_text != last_text:
                    if current_text.strip():
                        self._add_to_history(current_text)
                    last_text = current_text
            except Exception as e:
                self.logger.debug(f"Monitor iteration skipped: {e}")

            # Non-blocking sleep responsive to stop event
            self._stop_event.wait(timeout=2.0)

    def _setup_routes(self):
        @self.router.get("/history")
        async def get_history():
            return self.history

        @self.router.post("/copy")
        async def copy_content(item: Dict[str, Any] = Body(...)):
            content = str(item.get("content", ""))
            if content:
                success = await asyncio.to_thread(self.clipboard.set_text, content)
                if success:
                    self._add_to_history(content)
                    return {"status": "success", "message": "Copied to PC clipboard"}
                raise HTTPException(status_code=500, detail="Failed to write to OS clipboard")
            raise HTTPException(status_code=400, detail="No content provided")

        @self.router.post("/clear")
        async def clear_history():
            self.history = []
            self._persist_history_debounced()
            return {"status": "success"}

        @self.router.delete("/history/{item_id}")
        async def delete_item(item_id: int):
            self.history = [i for i in self.history if i.get("id") != item_id]
            self._persist_history_debounced()
            return {"status": "deleted"}

    def initialize(self) -> bool:
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name=f"pclink-clipmon-{self.metadata.id}",
        )
        self._monitor_thread.start()
        self.logger.info("Clipboard History v2 worker active (non-blocking monitoring).")
        return True

    def cleanup(self):
        self._stop_event.set()
        if self._save_debounce_timer:
            self._save_debounce_timer.cancel()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.5)
        self.logger.info("Clipboard History v2 worker stopped cleanly.")

    def get_routes(self) -> APIRouter:
        return self.router
