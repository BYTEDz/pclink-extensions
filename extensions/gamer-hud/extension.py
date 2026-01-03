import asyncio
import psutil
import subprocess
import shutil
from fastapi import APIRouter
from pclink.core.extension_base import ExtensionBase

class Extension(ExtensionBase):
    def __init__(self, metadata, extension_path, config: dict):
        super().__init__(metadata, extension_path, config)
        self.setup_routes()
        self._gpu_type = self._detect_gpu_type()

    def _detect_gpu_type(self):
        """Detect if we have an NVIDIA GPU by checking for nvidia-smi."""
        if shutil.which("nvidia-smi"):
            return "nvidia"
        return "generic"

    def _get_gpu_stats(self):
        """Try to get GPU usage/temp. Currently supports NVIDIA via nvidia-smi."""
        stats = {"usage": 0, "temp": 0, "memory": 0, "name": "Generic GPU"}
        
        if self._gpu_type == "nvidia":
            try:
                # Run nvidia-smi to get usage, temp, and memory
                # Query: name, utilization.gpu, temperature.gpu, memory.used, memory.total
                cmd = ["nvidia-smi", "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"]
                result = subprocess.check_output(cmd, encoding='utf-8', timeout=1).strip()
                name, usage, temp, mem_used, mem_total = result.split(", ")
                stats = {
                    "usage": int(usage),
                    "temp": int(temp),
                    "memory": int(int(mem_used) / int(mem_total) * 100),
                    "name": name
                }
            except Exception as e:
                self.logger.warning(f"Failed to get NVIDIA stats: {e}")
        
        return stats

    def setup_routes(self):
        @self.router.get("/stats")
        async def get_stats():
            cpu_usage = psutil.cpu_percent(interval=None)
            cpu_freq = psutil.cpu_freq()
            ram = psutil.virtual_memory()
            
            # Per-core usage for specialized HUD
            cpu_cores = psutil.cpu_percent(interval=None, percpu=True)
            
            gpu_stats = self._get_gpu_stats()
            
            return {
                "cpu": {
                    "usage": cpu_usage,
                    "freq": round(cpu_freq.current / 1000, 2) if cpu_freq else 0,
                    "cores": cpu_cores
                },
                "ram": {
                    "usage": ram.percent,
                    "used": round(ram.used / (1024**3), 2),
                    "total": round(ram.total / (1024**3), 2)
                },
                "gpu": gpu_stats,
                "uptime": round((asyncio.get_event_loop().time()), 0) # Relative session uptime
            }

    def initialize(self) -> bool:
        # Priming psutil for first call
        psutil.cpu_percent(interval=None)
        self.logger.info("Gamer HUD Extension initialized.")
        return True

    def cleanup(self):
        self.logger.info("Gamer HUD Extension shutting down.")

    def get_routes(self) -> APIRouter:
        return self.router
