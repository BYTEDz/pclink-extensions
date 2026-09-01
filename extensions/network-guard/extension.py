# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 AZHAR ZOUHIR / BYTEDz

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil
from fastapi import APIRouter, Body, HTTPException

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
        try:
            self.last_net_io = psutil.net_io_counters()
        except Exception:
            self.last_net_io = None
        self.last_time = time.time()
        self._setup_routes()

    def _get_network_speed(self) -> Dict[str, float]:
        try:
            current_net_io = psutil.net_io_counters()
        except Exception:
            return {"down": 0.0, "up": 0.0}

        current_time = time.time()
        elapsed = current_time - self.last_time
        if elapsed <= 0 or not self.last_net_io:
            self.last_net_io = current_net_io
            self.last_time = current_time
            return {"down": 0.0, "up": 0.0}

        down = (current_net_io.bytes_recv - self.last_net_io.bytes_recv) / elapsed
        up = (current_net_io.bytes_sent - self.last_net_io.bytes_sent) / elapsed

        self.last_net_io = current_net_io
        self.last_time = current_time

        return {
            "down": round(max(0.0, down / 1024), 2),  # KB/s
            "up": round(max(0.0, up / 1024), 2),      # KB/s
        }

    def _get_active_apps(self) -> List[Dict[str, Any]]:
        apps = []
        try:
            connections = psutil.net_connections(kind="inet")
            pid_map: Dict[int, Dict[str, Any]] = {}
            for conn in connections:
                if conn.pid and conn.status == "ESTABLISHED":
                    if conn.pid not in pid_map:
                        pid_map[conn.pid] = {"remote": [], "count": 0}
                    if conn.raddr:
                        pid_map[conn.pid]["remote"].append(
                            f"{conn.raddr.ip}:{conn.raddr.port}"
                        )
                    pid_map[conn.pid]["count"] += 1

            for pid, info in pid_map.items():
                try:
                    p = psutil.Process(pid)
                    p_name = p.name()
                    if p_name in ("System", "System Idle Process"):
                        continue

                    apps.append(
                        {
                            "pid": pid,
                            "name": p_name,
                            "conn_count": info["count"],
                            "remote": info["remote"][:3],
                            "status": p.status(),
                        }
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            self.logger.error(f"Failed to inspect network sockets: {e}")

        apps.sort(key=lambda x: x["conn_count"], reverse=True)
        return apps[:20]

    def _setup_routes(self):
        @self.router.get("/status")
        async def get_status():
            return {
                "speed": self._get_network_speed(),
                "apps": self._get_active_apps(),
            }

        @self.router.post("/action")
        async def process_action(data: Dict[str, Any] = Body(...)):
            pid = data.get("pid")
            action = data.get("action")

            if not pid or not action:
                raise HTTPException(status_code=400, detail="Missing pid or action")

            try:
                p = psutil.Process(int(pid))
                if action == "kill":
                    p.kill()
                    return {"status": "killed", "pid": pid}
                elif action == "suspend":
                    p.suspend()
                    return {"status": "suspended", "pid": pid}
                elif action == "resume":
                    p.resume()
                    return {"status": "resumed", "pid": pid}
                else:
                    raise HTTPException(status_code=400, detail="Invalid action")
            except psutil.NoSuchProcess:
                raise HTTPException(status_code=404, detail=f"Process {pid} not found")
            except psutil.AccessDenied:
                raise HTTPException(status_code=403, detail=f"Access denied for process {pid}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    def initialize(self) -> bool:
        self.logger.info("Network Guard v2 isolated worker active.")
        return True

    def cleanup(self):
        self.logger.info("Network Guard v2 isolated worker stopped.")

    def get_routes(self) -> APIRouter:
        return self.router
