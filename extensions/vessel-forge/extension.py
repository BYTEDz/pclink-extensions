import os
import sys
import threading
import time
import json
from fastapi import APIRouter, Body, HTTPException
from typing import Dict, List, Optional
from pclink.core.extension_base import ExtensionBase

# Add Bundled Libs
LIB_DIR = os.path.join(os.path.dirname(__file__), "lib")
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

try:
    import docker
    from docker.errors import DockerException
    HAS_DOCKER = True
except ImportError:
    HAS_DOCKER = False

class Extension(ExtensionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client: Optional['docker.DockerClient'] = None
        self._pulling = {} 
        self._deploying = {}
        self._lock = threading.Lock()
        self.setup_routes()

    def _get_client(self):
        if self.client:
            try:
                self.client.ping()
                return self.client
            except:
                self.client = None
        if not HAS_DOCKER: return None
        try:
            self.client = docker.from_env()
            self.client.ping()
            return self.client
        except: return None

    def setup_routes(self):
        @self.router.get("/status")
        async def get_status():
            client = self._get_client()
            if not client: return {"connected": False}
            try:
                containers = client.containers.list(all=True)
                with self._lock: 
                    pulling = dict(self._pulling)
                    deploying = dict(self._deploying)
                return {
                    "connected": True,
                    "total": len(containers),
                    "running": len([c for c in containers if c.status == 'running']),
                    "pulling": pulling,
                    "deploying": deploying
                }
            except: return {"connected": False}

        @self.router.get("/containers")
        async def list_containers():
            client = self._get_client()
            if not client: raise HTTPException(status_code=503)
            data = []
            for c in client.containers.list(all=True):
                attrs = c.attrs
                # Get the last error if it failed to start
                state = attrs.get('State', {})
                error = state.get('Error', '')
                
                data.append({
                    "id": c.short_id,
                    "name": c.name,
                    "status": c.status,
                    "error": error,
                    "image": attrs.get('Config', {}).get('Image'),
                    "created": attrs.get('Created'),
                    "started_at": state.get('StartedAt'),
                    "command": " ".join(attrs.get('Config', {}).get('Cmd', []) or []),
                    "ports": attrs.get('NetworkSettings', {}).get('Ports', {}),
                    "networks": list(attrs.get('NetworkSettings', {}).get('Networks', {}).keys()),
                    "mounts": [{"src": m.get('Source'), "dst": m.get('Destination')} for m in attrs.get('Mounts', [])],
                    "env": [e for e in attrs.get('Config', {}).get('Env', []) if not any(x in e.lower() for x in ['pass', 'key', 'secret', 'token'])] 
                })
            return data

        @self.router.post("/containers/run")
        async def run_container(payload: dict = Body(...)):
            client = self._get_client()
            if not client: raise HTTPException(status_code=503)
            try:
                mode = payload.get("mode", "basic")
                run_kwargs = {"detach": True}

                if mode == "advanced":
                    run_kwargs.update(payload.get("config", {}))
                else:
                    image = payload.get("image")
                    if not image: raise Exception("Image is required")
                    run_kwargs["image"] = image
                    run_kwargs["name"] = payload.get("name") or None
                    if payload.get("ports") and ":" in payload.get("ports"):
                        h, c = payload.get("ports").split(":")
                        run_kwargs["ports"] = {f"{c}/tcp": int(h)}
                    if payload.get("env"):
                        run_kwargs["environment"] = payload.get("env").split(",")
                    if payload.get("volumes") and ":" in payload.get("volumes"):
                        # Use named volume logic or ensure path exists logic
                        h, c = payload.get("volumes").split(":")
                        run_kwargs["volumes"] = {h: {'bind': c, 'mode': 'rw'}}

                def do_run(kwargs, task_id):
                    try:
                        client.containers.run(**kwargs)
                    finally:
                        with self._lock: self._deploying.pop(task_id, None)

                task_id = payload.get("name") or payload.get("image") or "new-container"
                with self._lock: self._deploying[task_id] = "Launching..."
                threading.Thread(target=do_run, args=(run_kwargs, task_id), daemon=True).start()
                return {"success": True}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @self.router.post("/containers/{id}/{action}")
        async def container_action(id: str, action: str):
            client = self._get_client()
            c = client.containers.get(id)
            if action == "start": c.start()
            elif action == "stop": c.stop()
            elif action == "remove": c.remove(force=True)
            return {"success": True}

        @self.router.get("/containers/{id}/logs")
        async def get_logs(id: str, tail: int = 200):
            client = self._get_client()
            c = client.containers.get(id)
            return {"logs": c.logs(tail=tail).decode('utf-8', errors='ignore')}

        @self.router.get("/images")
        async def list_images():
            client = self._get_client()
            return [{"id": i.short_id, "tags": i.tags, "size": i.attrs.get('Size', 0)} for i in client.images.list()]

        @self.router.post("/containers/bulk/{action}")
        async def bulk_action(action: str):
            client = self._get_client()
            if not client: raise HTTPException(status_code=503)
            containers = client.containers.list(all=True)
            for c in containers:
                try:
                    if action == "start": c.start()
                    elif action == "stop": c.stop()
                except: continue
            return {"success": True}

        @self.router.post("/system/prune")
        async def prune_system():
            client = self._get_client()
            if not client: raise HTTPException(status_code=503)
            client.containers.prune()
            return {"success": True}

        @self.router.post("/images/pull")
        async def pull_image(image: str = Body(..., embed=True)):
            client = self._get_client()
            def do_pull(repo):
                with self._lock: self._pulling[repo] = "Starting..."
                try: client.images.pull(repo)
                finally:
                    with self._lock: self._pulling.pop(repo, None)
            threading.Thread(target=do_pull, args=(image,), daemon=True).start()
            return {"success": True}

        @self.router.delete("/images/{id}")
        async def delete_image(id: str):
            client = self._get_client()
            client.images.remove(id, force=True)
            return {"success": True}

    def initialize(self) -> bool: return True
    def cleanup(self): 
        if self.client: self.client.close()
    def get_routes(self) -> APIRouter: return self.router