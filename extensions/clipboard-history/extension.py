import threading
import time
import ctypes
import json
import logging
from pathlib import Path
from fastapi import APIRouter, Body
from typing import List, Dict, Optional
from ctypes import wintypes
from pclink.core.extension_base import ExtensionBase

# --- Windows Clipboard Ctypes Wrapper ---
class Clipboard:
    def __init__(self):
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        
        self.CF_UNICODETEXT = 13
        
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
        
        self.GMEM_MOVEABLE = 0x0002

    def get_text(self) -> Optional[str]:
        for _ in range(5):  # Retry up to 5 times
            try:
                if self.user32.OpenClipboard(None):
                    break
            except Exception:
                pass
            time.sleep(0.1)
        else:
            return None  # Failed to open clipboard
        
        text = None
        try:
            h_data = self.user32.GetClipboardData(self.CF_UNICODETEXT)
            if h_data:
                p_data = self.kernel32.GlobalLock(h_data)
                if p_data:
                    text = ctypes.c_wchar_p(p_data).value
                    self.kernel32.GlobalUnlock(h_data)
        except Exception:
            pass # Silent failure for clipboard access
        finally:
            self.user32.CloseClipboard()
            
        return text

    def set_text(self, text: str) -> bool:
        for _ in range(5):
            try:
                if self.user32.OpenClipboard(None):
                    break
            except Exception:
                pass
            time.sleep(0.1)
        else:
            return False

        try:
            self.user32.EmptyClipboard()
            
            # Allocate global memory
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
        except Exception:
            pass
        finally:
            self.user32.CloseClipboard()
        return False

class Extension(ExtensionBase):
    def __init__(self, metadata, extension_path, config: dict):
        super().__init__(metadata, extension_path, config)
        self.history_file = self.extension_path / "history.json"
        self.clipboard = Clipboard()
        
        self.history: List[Dict] = []
        self._load_history()
        
        self.running = False
        self.monitor_thread = None
        
        self.setup_routes()

    def setup_routes(self):
        @self.router.get("/history")
        async def get_history():
            return self.history

        @self.router.post("/copy")
        async def copy_content(item: Dict = Body(...)):
            content = item.get("content")
            if content:
                self.clipboard.set_text(content)
                # We update history immediately just in case, though the monitor would catch it too
                self._add_to_history(content)
                return {"status": "success", "message": "Copied to PC clipboard"}
            return {"status": "error", "message": "No content provided"}

        @self.router.post("/clear")
        async def clear_history():
            self.history = []
            self._save_history()
            return {"status": "success"}

    def initialize(self) -> bool:
        self.logger.info("Clipboard History Extension initialized.")
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        return True

    def cleanup(self):
        self.logger.info("Clipboard History Extension shutting down.")
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1.0)

    def _monitor_loop(self):
        last_text = self.clipboard.get_text()
        
        while self.running:
            try:
                current_text = self.clipboard.get_text()
                if current_text and current_text != last_text:
                    if current_text.strip(): # Ignore empty strings
                        self._add_to_history(current_text)
                        last_text = current_text
            except Exception as e:
                self.logger.error(f"Error in clipboard monitor: {e}")
            
            time.sleep(1.0) # Check every second

    def _add_to_history(self, content: str):
        # Avoid duplicates at the top
        if self.history and self.history[0]["content"] == content:
            return

        entry = {
            "id": int(time.time() * 1000),
            "content": content,
            "timestamp": time.time(),
            "type": "text" 
        }
        
        self.history.insert(0, entry)
        
        # Keep only last 50 items
        if len(self.history) > 50:
            self.history = self.history[:50]
            
        self._save_history()

    def _load_history(self):
        if self.history_file.exists():
            try:
                with open(self.history_file, "r") as f:
                    self.history = json.load(f)
            except:
                self.history = []

    def _save_history(self):
        try:
            with open(self.history_file, "w") as f:
                json.dump(self.history, f)
        except Exception as e:
            self.logger.error(f"Failed to save clipboard history: {e}")
