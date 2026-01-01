import threading
import time
from fastapi import APIRouter, Body
from typing import Dict, Optional
from pclink.core.extension_base import ExtensionBase

# Import the bundled speedtest library
try:
    import speedtest
    HAS_SPEEDTEST = True
except ImportError:
    HAS_SPEEDTEST = False

class Extension(ExtensionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.running = True
        self.results = {
            "status": "idle", # idle, testing, complete, error
            "mode": "internet", # internet, lan
            "phase": "Ready",
            "download": 0,
            "upload": 0,
            "ping": 0,
            "server": "",
            "timestamp": 0
        }
        self.test_thread: Optional[threading.Thread] = None
        self.setup_routes()

    def setup_routes(self):
        @self.router.get("/status")
        async def get_status():
            return self.results

        @self.router.post("/start")
        async def start_test():
            if self.results["status"] == "testing":
                return {"status": "error", "message": "Test already in progress"}
            
            if not HAS_SPEEDTEST:
                return {"status": "error", "message": "Speedtest library not found"}

            self.results["mode"] = "internet"
            self.results["status"] = "testing"
            self.results["phase"] = "Initializing"
            self.results["download"] = 0
            self.results["upload"] = 0
            self.results["ping"] = 0
            
            self.test_thread = threading.Thread(target=self._run_speed_test, daemon=True)
            self.test_thread.start()
            return {"status": "success"}

        # LOCAL SPEED TEST ENDPOINTS
        @self.router.get("/local/download")
        async def local_download():
            # Return 50MB of dummy data for speed testing
            # We use a generator to keep memory low
            def generate_data():
                chunk = b"0" * (1024 * 1024) # 1MB chunk
                for _ in range(50):
                    yield chunk
            
            from fastapi.responses import StreamingResponse
            return StreamingResponse(generate_data(), media_type="application/octet-stream")

        @self.router.post("/local/upload")
        async def local_upload(data: bytes = Body(...)):
            # Just receive data and return size to confirm
            return {"received": len(data)}

        @self.router.post("/local/results")
        async def save_local_results(data: Dict = Body(...)):
            self.results.update({
                "mode": "lan",
                "status": "complete",
                "phase": "Finished",
                "download": data.get("download", 0),
                "upload": data.get("upload", 0),
                "ping": data.get("ping", 0),
                "server": "Local PCLink Server",
                "timestamp": time.time()
            })
            return {"status": "success"}

    def _run_speed_test(self):
        try:
            # We use secure=True to avoid 403 errors and connection issues
            st = speedtest.Speedtest(secure=True)
            
            self.results["phase"] = "Finding Server"
            st.get_servers()
            st.get_best_server()
            
            self.results["ping"] = st.results.ping
            self.results["server"] = f"{st.results.server['name']}, {st.results.server['country']}"
            
            self.results["phase"] = "Testing Download"
            self.results["download"] = st.download() / 1_000_000 # Mbps
            
            self.results["phase"] = "Testing Upload"
            self.results["upload"] = st.upload() / 1_000_000 # Mbps
            
            self.results["status"] = "complete"
            self.results["phase"] = "Finished"
            self.results["timestamp"] = time.time()
        except Exception as e:
            self.logger.error(f"Speed test failed: {e}")
            self.results["status"] = "error"
            self.results["error_message"] = str(e)

    def initialize(self) -> bool:
        self.logger.info("Speed Test Extension initialized.")
        return True

    def cleanup(self):
        self.running = False

    def get_routes(self) -> APIRouter:
        return self.router
