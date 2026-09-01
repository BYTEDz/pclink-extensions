# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 AZHAR ZOUHIR / BYTEDz

import asyncio
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil
from fastapi import APIRouter

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
        self.is_windows = sys.platform == "win32"
        self.is_linux = sys.platform.startswith("linux")
        self._has_nvidia = shutil.which("nvidia-smi") is not None
        self._cached_gpu_name = self._detect_gpu_name()
        self._setup_routes()

    def _detect_gpu_name(self) -> str:
        if self._has_nvidia:
            try:
                cmd = ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"]
                kwargs = {"capture_output": True, "text": True, "timeout": 2.0}
                if self.is_windows:
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                res = subprocess.run(cmd, **kwargs)
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip().splitlines()[0]
            except Exception:
                pass

        if self.is_linux:
            # Check Linux sysfs DRM devices
            drm_path = Path("/sys/class/drm")
            if drm_path.exists():
                for card in drm_path.glob("card[0-9]"):
                    device_name = card / "device" / "vendor"
                    if device_name.exists():
                        return "Integrated / Dedicated GPU"

        return "GPU Accelerator"

    def _get_cpu_thermals(self) -> float:
        if self.is_linux:
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for key in ["coretemp", "k10temp", "cpu_thermal", "acpitz", "zenpower"]:
                        if key in temps and temps[key]:
                            return round(temps[key][0].current, 1)
            except Exception:
                pass
        return 0.0

    def _get_gpu_stats(self) -> Dict[str, Any]:
        stats = {
            "usage": 0,
            "temp": 0,
            "memory_used_mb": 0,
            "memory_total_mb": 0,
            "memory_pct": 0,
            "name": self._cached_gpu_name,
        }

        # 1. NVIDIA via nvidia-smi
        if self._has_nvidia:
            try:
                cmd = [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ]
                kwargs = {"capture_output": True, "text": True, "timeout": 1.5}
                if self.is_windows:
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                res = subprocess.run(cmd, **kwargs)
                if res.returncode == 0 and res.stdout.strip():
                    parts = [p.strip() for p in res.stdout.strip().split(",")]
                    if len(parts) >= 4:
                        usage = int(parts[0]) if parts[0].isdigit() else 0
                        temp = int(parts[1]) if parts[1].isdigit() else 0
                        mem_used = int(parts[2]) if parts[2].isdigit() else 0
                        mem_total = int(parts[3]) if parts[3].isdigit() else 1
                        mem_pct = round((mem_used / max(1, mem_total)) * 100, 1)

                        stats.update(
                            {
                                "usage": usage,
                                "temp": temp,
                                "memory_used_mb": mem_used,
                                "memory_total_mb": mem_total,
                                "memory_pct": mem_pct,
                            }
                        )
                        return stats
            except Exception:
                pass

        # 2. Linux AMD/Intel GPU via sysfs
        if self.is_linux:
            try:
                busy_path = Path("/sys/class/drm/card0/device/gpu_busy_percent")
                if busy_path.exists():
                    usage = int(busy_path.read_text().strip())
                    stats["usage"] = usage

                # Read AMD/Intel thermal sensor
                for hwmon in Path("/sys/class/hwmon").glob("hwmon*"):
                    name_file = hwmon / "name"
                    if name_file.exists() and any(
                        x in name_file.read_text().lower() for x in ["amdgpu", "radeon", "i915"]
                    ):
                        temp_file = hwmon / "temp1_input"
                        if temp_file.exists():
                            stats["temp"] = int(int(temp_file.read_text().strip()) / 1000)
                            break
            except Exception:
                pass

        return stats

    def _collect_telemetry_sync(self) -> Dict[str, Any]:
        cpu_usage = psutil.cpu_percent(interval=None)
        cpu_cores = psutil.cpu_percent(interval=None, percpu=True)
        cpu_freq = psutil.cpu_freq()
        ram = psutil.virtual_memory()

        gpu_data = self._get_gpu_stats()
        cpu_temp = self._get_cpu_thermals()

        return {
            "cpu": {
                "usage": round(cpu_usage, 1),
                "freq_ghz": round(cpu_freq.current / 1000, 2) if cpu_freq else 0.0,
                "cores": [round(c, 1) for c in cpu_cores],
                "temp": cpu_temp,
            },
            "ram": {
                "usage": round(ram.percent, 1),
                "used_gb": round(ram.used / (1024**3), 2),
                "total_gb": round(ram.total / (1024**3), 2),
            },
            "gpu": gpu_data,
        }

    def _setup_routes(self):
        @self.router.get("/stats")
        async def get_hardware_stats():
            return await asyncio.to_thread(self._collect_telemetry_sync)

    def initialize(self) -> bool:
        # Prime psutil baseline
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)
        self.logger.info("Gamer HUD Pro v2 worker active.")
        return True

    def cleanup(self):
        self.logger.info("Gamer HUD Pro v2 shutting down.")

    def get_routes(self) -> APIRouter:
        return self.router
