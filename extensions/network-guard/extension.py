import psutil
import time
import asyncio
from fastapi import APIRouter, HTTPException, Body
from typing import List, Dict
from pclink.core.extension_base import ExtensionBase

class Extension(ExtensionBase):
    def __init__(self, metadata, extension_path, config: dict):
        super().__init__(metadata, extension_path, config)
        self.last_net_io = psutil.net_io_counters()
        self.last_time = time.time()
        self.setup_routes()

    def _get_network_speed(self):
        """Calculate global download and upload speed."""
        current_net_io = psutil.net_io_counters()
        current_time = time.time()
        
        elapsed = current_time - self.last_time
        if elapsed <= 0:
            return {"down": 0, "up": 0}
            
        down = (current_net_io.bytes_recv - self.last_net_io.bytes_recv) / elapsed
        up = (current_net_io.bytes_sent - self.last_net_io.bytes_sent) / elapsed
        
        self.last_net_io = current_net_io
        self.last_time = current_time
        
        return {
            "down": round(down / 1024, 2), # KB/s
            "up": round(up / 1024, 2)      # KB/s
        }

    def _get_active_apps(self):
        """Get processes with active network connections."""
        apps = []
        try:
            connections = psutil.net_connections(kind='inet')
            pid_map = {}
            for conn in connections:
                if conn.pid and conn.status == 'ESTABLISHED':
                    if conn.pid not in pid_map:
                        pid_map[conn.pid] = {"remote": [], "count": 0}
                    if conn.raddr:
                        pid_map[conn.pid]["remote"].append(f"{conn.raddr.ip}:{conn.raddr.port}")
                    pid_map[conn.pid]["count"] += 1

            for pid, info in pid_map.items():
                try:
                    p = psutil.Process(pid)
                    if p.name() == "System": continue
                    
                    apps.append({
                        "pid": pid,
                        "name": p.name(),
                        "conn_count": info["count"],
                        "remote": info["remote"][:3], # Show first 3 connections
                        "status": p.status()
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            self.logger.error(f"Error getting network apps: {e}")
            
        # Sort by connection count
        apps.sort(key=lambda x: x["conn_count"], reverse=True)
        return apps[:15] # Top 15 apps

    def setup_routes(self):
        @self.router.get("/status")
        async def get_status():
            return {
                "speed": self._get_network_speed(),
                "apps": self._get_active_apps()
            }

        @self.router.post("/action")
        async def process_action(data: Dict = Body(...)):
            pid = data.get("pid")
            action = data.get("action")
            
            try:
                p = psutil.Process(pid)
                if action == "kill":
                    p.kill()
                    return {"status": "killed"}
                elif action == "suspend":
                    p.suspend()
                    return {"status": "suspended"}
                elif action == "resume":
                    p.resume()
                    return {"status": "resumed"}
                else:
                    raise HTTPException(status_code=400, detail="Invalid action")
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    def initialize(self) -> bool:
        self.logger.info("Network Guard Extension initialized.")
        return True

    def cleanup(self):
        self.logger.info("Network Guard Extension shutting down.")

    def get_routes(self) -> APIRouter:
        return self.router
