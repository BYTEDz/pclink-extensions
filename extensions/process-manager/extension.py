from pclink.core.extension_base import ExtensionBase
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psutil
import logging

# Data Models
class KillRequest(BaseModel):
    pid: int

class Extension(ExtensionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.router = APIRouter()
        self.setup_routes()

    def setup_routes(self):
        @self.router.get("/processes")
        async def get_processes(sort_by: str = "memory"):
            """
            Returns top 50 resource-consuming processes.
            """
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'username', 'memory_info', 'cpu_percent']):
                try:
                    # Filter out system idle tasks or empty names
                    if not p.info['name']:
                        continue
                        
                    mem_mb = round(p.info['memory_info'].rss / (1024 * 1024), 1)
                    
                    procs.append({
                        "pid": p.info['pid'],
                        "name": p.info['name'],
                        "user": p.info['username'],
                        "memory": mem_mb,
                        "cpu": p.info['cpu_percent'] or 0.0
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            # Sort data
            if sort_by == "cpu":
                procs.sort(key=lambda x: x['cpu'], reverse=True)
            else:
                procs.sort(key=lambda x: x['memory'], reverse=True)

            return {"status": "ok", "data": procs[:50]} # Limit to top 50 to keep UI snappy

        @self.router.post("/kill")
        async def kill_process(req: KillRequest):
            """
            Terminates a process by PID.
            """
            try:
                p = psutil.Process(req.pid)
                p.terminate() # Try graceful termination first
                try:
                    p.wait(timeout=3)
                except psutil.TimeoutExpired:
                    p.kill() # Force kill if it doesn't close
                
                self.logger.info(f"Killed process {req.pid}")
                return {"status": "ok", "message": f"Process {req.pid} terminated"}
            except psutil.NoSuchProcess:
                raise HTTPException(status_code=404, detail="Process not found")
            except psutil.AccessDenied:
                raise HTTPException(status_code=403, detail="Access denied")
            except Exception as e:
                self.logger.error(f"Error killing process: {e}")
                raise HTTPException(status_code=500, detail=str(e))

    def initialize(self) -> bool:
        self.logger.info("Process Manager Initialized")
        return True

    def cleanup(self):
        pass

    def get_routes(self) -> APIRouter:
        return self.router