# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 AZHAR ZOUHIR / BYTEDz

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse

from pclink.core.extension_base import ExtensionBase, ExtensionMetadata

log = logging.getLogger("pclink.speedtest")

try:
    import speedtest

    HAS_SPEEDTEST = True
except ImportError:
    HAS_SPEEDTEST = False


class Extension(ExtensionBase):
    def __init__(
        self,
        metadata: ExtensionMetadata,
        extension_path: Path,
        config: Dict[str, Any],
        context=None,
    ):
        super().__init__(metadata, extension_path, config, context)
        self.results: Dict[str, Any] = {
            "status": "idle",  # idle, testing, complete, error
            "mode": "internet",  # internet, lan
            "phase": "Ready",
            "download": 0.0,
            "upload": 0.0,
            "ping": 0.0,
            "server": "",
            "timestamp": 0,
            "error_message": None,
        }
        self._test_thread: Optional[threading.Thread] = None
        self._setup_routes()

    def _run_broadband_test(self):
        if not HAS_SPEEDTEST:
            self.results["status"] = "error"
            self.results["error_message"] = "speedtest module is not installed."
            return

        try:
            self.results["phase"] = "Selecting Server"
            st = speedtest.Speedtest(secure=True)
            st.get_servers()
            best = st.get_best_server()

            self.results["ping"] = round(float(st.results.ping), 1)
            self.results["server"] = f"{best.get('name', 'Unknown')}, {best.get('country', '')}"

            self.results["phase"] = "Testing Download"
            dl_speed = st.download() / 1_000_000.0  # Convert to Mbps
            self.results["download"] = round(dl_speed, 2)

            self.results["phase"] = "Testing Upload"
            ul_speed = st.upload() / 1_000_000.0  # Convert to Mbps
            self.results["upload"] = round(ul_speed, 2)

            self.results["status"] = "complete"
            self.results["phase"] = "Finished"
            self.results["timestamp"] = time.time()

        except Exception as e:
            self.logger.error(f"Broadband speed test error: {e}")
            self.results["status"] = "error"
            self.results["error_message"] = str(e)

    def _setup_routes(self):
        @self.router.get("/status")
        async def get_status():
            return self.results

        @self.router.get("/ping")
        async def ping_probe():
            """Lightweight probe endpoint for microsecond latency sampling."""
            return {"pong": True, "t": time.time()}

        @self.router.post("/start")
        async def start_broadband_test():
            if self.results["status"] == "testing":
                return {"status": "error", "message": "Test already active"}

            self.results["mode"] = "internet"
            self.results["status"] = "testing"
            self.results["phase"] = "Initializing"
            self.results["download"] = 0.0
            self.results["upload"] = 0.0
            self.results["ping"] = 0.0
            self.results["error_message"] = None

            self._test_thread = threading.Thread(
                target=self._run_broadband_test,
                daemon=True,
                name="pclink-speedtest-worker",
            )
            self._test_thread.start()
            return {"status": "success"}

        @self.router.get("/local/download")
        async def local_download_stream():
            """Streams 20MB of high-speed binary data for local link download test."""
            chunk = b"0" * 65536  # 64 KB chunk
            total_chunks = 320    # ~20 MB

            async def generate_chunks():
                for _ in range(total_chunks):
                    yield chunk
                    await asyncio.sleep(0)

            return StreamingResponse(
                generate_chunks(), media_type="application/octet-stream"
            )

        @self.router.post("/local/upload")
        async def local_upload_receiver(request: Request):
            """Receives upload payload stream to calculate throughput without memory bloat."""
            total_received = 0
            async for chunk in request.stream():
                total_received += len(chunk)
            return {"received_bytes": total_received}

        @self.router.post("/local/results")
        async def save_local_results(data: Dict[str, Any] = Body(...)):
            self.results.update(
                {
                    "mode": "lan",
                    "status": "complete",
                    "phase": "Finished",
                    "download": round(float(data.get("download", 0)), 2),
                    "upload": round(float(data.get("upload", 0)), 2),
                    "ping": round(float(data.get("ping", 0)), 1),
                    "server": "Local PCLink Host",
                    "timestamp": time.time(),
                    "error_message": None,
                }
            )
            return {"status": "success"}

    def initialize(self) -> bool:
        self.logger.info("Speed Engine v2 worker active.")
        return True

    def cleanup(self):
        self.logger.info("Speed Engine v2 shutting down.")

    def get_routes(self) -> APIRouter:
        return self.router
