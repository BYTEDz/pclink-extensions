import asyncio
import os
import shlex
import subprocess
import sys
from pclink.core.extension_base import ExtensionBase
from fastapi import APIRouter

class Extension(ExtensionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_routes()

    def setup_routes(self):
        @self.router.post("/exec")
        async def run_command(data: dict):
            cmd = data.get("command", "")
            shell = data.get("shell", False)
            timeout = data.get("timeout", 30)
            cwd = data.get("cwd", os.getcwd())
            try:
                if not cmd.strip():
                    return {"success": False, "error": "Empty command"}
                if shell:
                    proc = await asyncio.create_subprocess_shell(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        cwd=cwd
                    )
                else:
                    parts = shlex.split(cmd)
                    proc = await asyncio.create_subprocess_exec(
                        *parts, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        cwd=cwd
                    )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=timeout
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    return {
                        "success": False,
                        "error": f"Command timed out after {timeout}s",
                        "partial_stdout": "",
                        "partial_stderr": ""
                    }
                return {
                    "success": proc.returncode == 0,
                    "stdout": stdout.decode(errors="replace"),
                    "stderr": stderr.decode(errors="replace"),
                    "returncode": proc.returncode,
                    "cwd": cwd
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.router.get("/cwd")
        async def get_cwd():
            return {"cwd": os.getcwd()}

        @self.router.get("/env")
        async def get_env():
            return {
                "os": sys.platform,
                "cwd": os.getcwd(),
                "shell": os.environ.get("SHELL", os.environ.get("COMSPEC", ""))
            }

    def initialize(self) -> bool:
        return True

    def cleanup(self):
        pass

    def get_routes(self) -> APIRouter:
        return self.router

