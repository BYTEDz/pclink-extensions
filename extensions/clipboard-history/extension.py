import threading
import time
import json
import logging
import platform
import subprocess
import shutil
from pathlib import Path
from fastapi import APIRouter, Body
from typing import List, Dict, Optional
from pclink.core.extension_base import ExtensionBase

# Load Windows ctypes only if on Windows to prevent Linux crashes
OS_NAME = platform.system().lower()
if OS_NAME == "windows":
    import ctypes
    from ctypes import wintypes

# --- Cross-Platform Clipboard Wrapper ---
class Clipboard:
    def __init__(self):
        self.os_name = OS_NAME
        self.copy_cmd = None
        self.paste_cmd = None
        
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
        
        self.user32.OpenClipboard.argtypes = [wintypes.HWND]
        self.user32.OpenClipboard.restype = wintypes.BOOL
        self.user32.CloseClipboard.argtypes =[]
        self.user32.CloseClipboard.restype = wintypes.BOOL
        self.user32.GetClipboardData.argtypes = [wintypes.UINT]
        self.user32.GetClipboardData.restype = wintypes.HANDLE
        self.user32.EmptyClipboard.argtypes =[]
        self.user32.EmptyClipboard.restype = wintypes.BOOL
        self.user32.SetClipboardData.argtypes =[wintypes.UINT, wintypes.HANDLE]
        self.user32.SetClipboardData.restype = wintypes.HANDLE
        
        self.kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        self.kernel32.GlobalLock.restype = wintypes.LPVOID
        self.kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        self.kernel32.GlobalUnlock.restype = wintypes.BOOL
        self.kernel32.GlobalAlloc.argtypes =[wintypes.UINT, ctypes.c_size_t]
        self.kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        
        self.GMEM_MOVEABLE = 0x0002

    def _init_linux(self):
        # Detect whether the user uses Wayland or X11 and set the appropriate CLI tool
        if shutil.which("wl-copy") and shutil.which("wl-paste"):
            self.copy_cmd = ["wl-copy"]
            self.paste_cmd =["wl-paste", "-n"]
        elif shutil.which("xclip"):
            self.copy_cmd =["xclip", "-selection", "clipboard"]
            self.paste_cmd =["xclip", "-selection", "clipboard", "-o"]
        elif shutil.which("xsel"):
            self.copy_cmd = ["xsel", "-b", "-i"]
            self.paste_cmd =["xsel", "-b", "-o"]
        else:
            logging.warning("No clipboard utility found for Linux. Please install 'wl-clipboard', 'xclip', or 'xsel'.")

    def _init_mac(self):
        if shutil.which("pbcopy") and shutil.which("pbpaste"):
            self.copy_cmd = ["pbcopy"]
            self.paste_cmd = ["pbpaste"]

    def _get_text_windows(self) -> Optional[str]:
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

    def _set_text_windows(self, text: str) -> bool:
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

    def get_text(self) -> Optional[str]:
        if self.os_name == "windows":
            return self._get_text_windows()
        elif self.paste_cmd:
            try:
                result = subprocess.run(self.paste_cmd, capture_output=True)
                if result.returncode == 0:
                    return result.stdout.decode('utf-8')
            except UnicodeDecodeError:
                return None  # Ignore binary/image data on the clipboard
            except Exception as e:
                pass
        return None

    def set_text(self, text: str) -> bool:
        if self.os_name == "windows":
            return self._set_text_windows(text)
        elif self.copy_cmd:
            try:
                subprocess.run(self.copy_cmd, input=text.encode('utf-8'), check=True, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                return False
        return False

class Extension(ExtensionBase):
    def __init__(self, metadata, extension_path, config: dict):
        super().__init__(metadata, extension_path, config)
        self.history_file = self.extension_path / "history.json"
        self.clipboard = Clipboard()
        
        self.history: List[Dict] =[]
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
                self._add_to_history(content)
                return {"status": "success", "message": "Copied to PC clipboard"}
            return {"status": "error", "message": "No content provided"}

        @self.router.post("/clear")
        async def clear_history():
            self.history =[]
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
                self.history =[]

    def _save_history(self):
        try:
            with open(self.history_file, "w") as f:
                json.dump(self.history, f)
        except Exception as e:
            self.logger.error(f"Failed to save clipboard history: {e}")