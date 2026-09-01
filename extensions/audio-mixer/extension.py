# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 AZHAR ZOUHIR / BYTEDz

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException

from pclink.core.extension_base import ExtensionBase, ExtensionMetadata

log = logging.getLogger(__name__)

# Windows Core Audio support
HAS_PYCAW = False
if sys.platform == "win32":
    try:
        import pythoncom
        from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume

        HAS_PYCAW = True
    except ImportError:
        HAS_PYCAW = False


class Extension(ExtensionBase):
    def __init__(
        self,
        metadata: ExtensionMetadata,
        extension_path: Path,
        config: Dict[str, Any],
        context=None,
    ):
        super().__init__(metadata, extension_path, config, context)
        self.is_linux = sys.platform.startswith("linux")
        self.is_windows = sys.platform == "win32"
        self.has_pactl = shutil.which("pactl") is not None
        self._setup_routes()

    def _guess_icon(self, name: str) -> str:
        n = name.lower()
        if any(x in n for x in ["chrome", "edge", "firefox", "brave", "opera", "browser"]):
            return "globe"
        if any(x in n for x in ["spotify", "music", "rhythmbox", "amberol", "tidal"]):
            return "music"
        if any(x in n for x in ["discord", "telegram", "slack", "teams", "skype"]):
            return "message-circle"
        if any(x in n for x in ["vlc", "mpv", "player", "video", "celluloid", "totem"]):
            return "play-circle"
        if any(x in n for x in ["system", "master", "default", "output"]):
            return "speaker"
        if any(x in n for x in ["game", "steam", "heroic", "lutris", "wine"]):
            return "gamepad-2"
        return "volume-2"

    # --- Windows Implementation (pycaw / CoreAudio COM) ---

    def _scan_windows_sessions(self) -> List[Dict[str, Any]]:
        if not HAS_PYCAW:
            return [
                {
                    "id": "system",
                    "name": "System Sounds (pycaw missing)",
                    "volume": 1.0,
                    "muted": False,
                    "icon": "speaker",
                }
            ]

        sessions_out = []
        try:
            pythoncom.CoInitialize()
            sessions = AudioUtilities.GetAllSessions()
            grouped: Dict[str, Dict[str, Any]] = {}

            for session in sessions:
                try:
                    volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                    if session.Process:
                        raw_name = session.Process.name()
                        display_name = raw_name.replace(".exe", "")
                        session_id = raw_name
                    else:
                        display_name = "System Sounds"
                        session_id = "system"

                    if session_id not in grouped:
                        grouped[session_id] = {
                            "id": session_id,
                            "name": display_name,
                            "volume": round(volume.GetMasterVolume(), 2),
                            "muted": bool(volume.GetMute()),
                            "icon": self._guess_icon(display_name),
                        }
                except Exception:
                    continue

            sessions_out = sorted(
                grouped.values(),
                key=lambda x: (x["id"] != "system", x["name"].lower()),
            )
        except Exception as e:
            self.logger.error(f"Error scanning Windows audio sessions: {e}")
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
        return sessions_out

    def _set_windows_volume(self, target_id: str, level: float):
        if not HAS_PYCAW:
            return
        try:
            pythoncom.CoInitialize()
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                try:
                    curr_id = session.Process.name() if session.Process else "system"
                    if curr_id == target_id:
                        volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                        volume.SetMasterVolume(float(level), None)
                except Exception:
                    continue
        except Exception as e:
            self.logger.error(f"Error setting Windows volume: {e}")
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    def _set_windows_mute(self, target_id: str, muted: bool):
        if not HAS_PYCAW:
            return
        try:
            pythoncom.CoInitialize()
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                try:
                    curr_id = session.Process.name() if session.Process else "system"
                    if curr_id == target_id:
                        volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                        volume.SetMute(int(muted), None)
                except Exception:
                    continue
        except Exception as e:
            self.logger.error(f"Error setting Windows mute: {e}")
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    # --- Linux Implementation (PipeWire / PulseAudio via pactl) ---

    def _scan_linux_sessions(self) -> List[Dict[str, Any]]:
        sessions_out = []

        # 1. Master System Output
        try:
            master_vol = 1.0
            master_muted = False
            res = subprocess.run(
                ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            if res.returncode == 0 and res.stdout:
                m = re.search(r"(\d+)%", res.stdout)
                if m:
                    master_vol = round(int(m.group(1)) / 100.0, 2)

            res_mute = subprocess.run(
                ["pactl", "get-sink-mute", "@DEFAULT_SINK@"],
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            if res_mute.returncode == 0 and res_mute.stdout:
                master_muted = "yes" in res_mute.stdout.lower()

            sessions_out.append(
                {
                    "id": "system",
                    "name": "Master Volume",
                    "volume": master_vol,
                    "muted": master_muted,
                    "icon": "speaker",
                }
            )
        except Exception:
            pass

        # 2. Per-Application Audio Streams (Sink Inputs)
        if not self.has_pactl:
            return sessions_out

        try:
            res = subprocess.run(
                ["pactl", "list", "sink-inputs"],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if res.returncode != 0 or not res.stdout:
                return sessions_out

            blocks = res.stdout.split("Sink Input #")
            grouped_apps: Dict[str, Dict[str, Any]] = {}

            for block in blocks[1:]:
                lines = block.splitlines()
                if not lines:
                    continue
                input_id = lines[0].strip()

                name_match = re.search(
                    r'application\.name = "(.*?)"|media\.name = "(.*?)"|application\.process\.binary = "(.*?)"',
                    block,
                )
                app_name = "Application"
                if name_match:
                    app_name = next(x for x in name_match.groups() if x)

                vol_match = re.search(r"Volume:.*?(\d+)%", block)
                volume = round(int(vol_match.group(1)) / 100.0, 2) if vol_match else 1.0

                mute_match = re.search(r"Mute: (yes|no)", block, re.IGNORECASE)
                muted = mute_match.group(1).lower() == "yes" if mute_match else False

                if app_name not in grouped_apps:
                    grouped_apps[app_name] = {
                        "id": input_id,
                        "name": app_name,
                        "volume": volume,
                        "muted": muted,
                        "icon": self._guess_icon(app_name),
                    }

            sessions_out.extend(
                sorted(grouped_apps.values(), key=lambda x: x["name"].lower())
            )
        except Exception as e:
            self.logger.debug(f"Error scanning Linux audio streams: {e}")

        return sessions_out

    def _set_linux_volume(self, target_id: str, level: float):
        pct = f"{int(round(level * 100))}%"
        try:
            if target_id == "system":
                subprocess.run(
                    ["pactl", "set-sink-volume", "@DEFAULT_SINK@", pct],
                    capture_output=True,
                    timeout=1.5,
                )
            else:
                subprocess.run(
                    ["pactl", "set-sink-input-volume", target_id, pct],
                    capture_output=True,
                    timeout=1.5,
                )
        except Exception as e:
            self.logger.debug(f"Error setting Linux volume for {target_id}: {e}")

    def _set_linux_mute(self, target_id: str, muted: bool):
        val = "1" if muted else "0"
        try:
            if target_id == "system":
                subprocess.run(
                    ["pactl", "set-sink-mute", "@DEFAULT_SINK@", val],
                    capture_output=True,
                    timeout=1.5,
                )
            else:
                subprocess.run(
                    ["pactl", "set-sink-input-mute", target_id, val],
                    capture_output=True,
                    timeout=1.5,
                )
        except Exception as e:
            self.logger.debug(f"Error setting Linux mute for {target_id}: {e}")

    def _setup_routes(self):
        @self.router.get("/sessions")
        async def get_sessions():
            if self.is_windows:
                return await asyncio.to_thread(self._scan_windows_sessions)
            elif self.is_linux:
                return await asyncio.to_thread(self._scan_linux_sessions)
            return [
                {
                    "id": "system",
                    "name": "System Audio",
                    "volume": 1.0,
                    "muted": False,
                    "icon": "speaker",
                }
            ]

        @self.router.post("/volume")
        async def set_volume(data: Dict[str, Any] = Body(...)):
            target_id = str(data.get("id", "system"))
            volume = float(data.get("volume", 1.0))
            if self.is_windows:
                await asyncio.to_thread(self._set_windows_volume, target_id, volume)
            elif self.is_linux:
                await asyncio.to_thread(self._set_linux_volume, target_id, volume)
            return {"status": "ok", "id": target_id, "volume": volume}

        @self.router.post("/mute")
        async def toggle_mute(data: Dict[str, Any] = Body(...)):
            target_id = str(data.get("id", "system"))
            muted = bool(data.get("muted", False))
            if self.is_windows:
                await asyncio.to_thread(self._set_windows_mute, target_id, muted)
            elif self.is_linux:
                await asyncio.to_thread(self._set_linux_mute, target_id, muted)
            return {"status": "ok", "id": target_id, "muted": muted}

    def initialize(self) -> bool:
        self.logger.info("Audio Mixer Pro v2 cross-platform worker initialized.")
        return True

    def cleanup(self):
        self.logger.info("Audio Mixer Pro v2 shutting down.")

    def get_routes(self) -> APIRouter:
        return self.router
