import logging
import pythoncom
import base64
from pclink.core.extension_base import ExtensionBase
from fastapi import APIRouter, Body
from typing import List, Dict

# Check dependencies
try:
    from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False

class Extension(ExtensionBase):
    def __init__(self, metadata, extension_path, config: dict):
        super().__init__(metadata, extension_path, config)
        self.setup_routes()

    def setup_routes(self):
        @self.router.get("/sessions")
        async def get_sessions():
            if not HAS_PYCAW:
                return [{
                    "id": "demo", 
                    "name": "Dependency Missing (Install pycaw)", 
                    "volume": 0.5, 
                    "muted": False,
                    "icon": "alert-triangle"
                }]
            return self._scan_audio_sessions()

        @self.router.post("/volume")
        async def set_volume(data: Dict = Body(...)):
            if not HAS_PYCAW: return {"error": "Missing dependencies"}
            self._set_session_volume(data['id'], data['volume'])
            return {"status": "ok"}

        @self.router.post("/mute")
        async def toggle_mute(data: Dict = Body(...)):
            if not HAS_PYCAW: return {"error": "Missing dependencies"}
            self._set_session_mute(data['id'], data['muted'])
            return {"status": "ok"}

    def _scan_audio_sessions(self):
        sessions_out = []
        try:
            pythoncom.CoInitialize()
            sessions = AudioUtilities.GetAllSessions()
            
            # Group by process name to avoid multiple sliders for the same app
            grouped = {}

            for session in sessions:
                try:
                    volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                    if session.Process:
                        # Full name like 'chrome.exe'
                        raw_name = session.Process.name()
                        display_name = raw_name.replace(".exe", "")
                        session_id = raw_name # Use 'chrome.exe' as stable ID
                    else:
                        display_name = "System Sounds"
                        session_id = "system"
                    
                    if session_id not in grouped:
                        grouped[session_id] = {
                            "id": session_id,
                            "name": display_name,
                            "volume": volume.GetMasterVolume(),
                            "muted": bool(volume.GetMute()),
                            "icon": self._guess_icon(display_name)
                        }
                    else:
                        # If we have multiple sessions, we just keep the first one's state 
                        # for the UI, but we'll update all of them together.
                        pass
                except Exception:
                    continue
            
            # Sort: System Sounds first, then alphabetical
            sessions_out = sorted(
                grouped.values(), 
                key=lambda x: (x['id'] != 'system', x['name'].lower())
            )
        except Exception as e:
            self.logger.error(f"Error scanning audio sessions: {e}")
        finally:
            pythoncom.CoUninitialize()
        return sessions_out

    def _set_session_volume(self, target_id, level):
        try:
            pythoncom.CoInitialize()
            sessions = AudioUtilities.GetAllSessions()
            self.logger.info(f"Setting volume for {target_id} to {level}")
            
            count = 0
            for session in sessions:
                try:
                    if session.Process:
                        current_id = session.Process.name()
                    else:
                        current_id = "system"

                    if current_id == target_id:
                        volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                        volume.SetMasterVolume(float(level), None)
                        count += 1
                except Exception:
                    continue
            
            if count == 0:
                self.logger.warning(f"No audio sessions found matching ID: {target_id}")
            else:
                self.logger.info(f"Updated {count} sessions for {target_id}")
        except Exception as e:
            self.logger.error(f"Error setting volume for {target_id}: {e}")
        finally:
            pythoncom.CoUninitialize()

    def _set_session_mute(self, target_id, muted):
        try:
            pythoncom.CoInitialize()
            sessions = AudioUtilities.GetAllSessions()
            
            for session in sessions:
                try:
                    if session.Process:
                        current_id = session.Process.name()
                    else:
                        current_id = "system"

                    if current_id == target_id:
                        volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                        volume.SetMute(int(muted), None)
                except Exception:
                    continue
        except Exception as e:
            self.logger.error(f"Error setting mute for {target_id}: {e}")
        finally:
            pythoncom.CoUninitialize()

    def _guess_icon(self, name):
        name = name.lower()
        if "chrome" in name or "edge" in name or "firefox" in name: return "globe"
        if "spotify" in name: return "music"
        if "discord" in name: return "message-circle"
        if "vlc" in name or "player" in name: return "play-circle"
        if "system" in name: return "speaker"
        return "box"

    def initialize(self) -> bool:
        self.logger.info("Audio Mixer Extension initialized.")
        return True

    def cleanup(self):
        pass

    def get_routes(self) -> APIRouter:
        return self.router
