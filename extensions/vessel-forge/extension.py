# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 AZHAR ZOUHIR / BYTEDz

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException

from pclink.core.extension_base import ExtensionBase, ExtensionMetadata

log = logging.getLogger(__name__)

LIB_DIR = os.path.join(os.path.dirname(__file__), "lib")
if os.path.exists(LIB_DIR) and LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

try:
    import docker
    from docker.errors import DockerException, NotFound, APIError

    HAS_DOCKER = True
except ImportError:
    HAS_DOCKER = False


class Extension(ExtensionBase):
    def __init__(
        self,
        metadata: ExtensionMetadata,
        extension_path: Path,
        config: Dict[str, Any],
        context=None,
    ):
        super().__init__(metadata, extension_path, config, context)
        self.client: Optional["docker.DockerClient"] = None
        self._pulling: Dict[str, str] = {}
        self._deploying: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._setup_routes()

    def _get_client(self) -> Optional["docker.DockerClient"]:
        if self.client:
            try:
                self.client.ping()
                return self.client
            except Exception:
                self.client = None

        if not HAS_DOCKER:
            return None

        try:
            self.client = docker.from_env(timeout=5)
            self.client.ping()
            return self.client
        except Exception as e:
            self.logger.debug(f"Docker client initialization error: {e}")
            return None

    def _setup_routes(self):
        @self.router.get("/status")
        async def get_status():
            client = self._get_client()
            if not client:
                return {"connected": False}
            try:
                containers = client.containers.list(all=True)
                with self._lock:
                    pulling = dict(self._pulling)
                    deploying = dict(self._deploying)
                return {
                    "connected": True,
                    "total": len(containers),
                    "running": len([c for c in containers if c.status == "running"]),
                    "pulling": pulling,
                    "deploying": deploying,
                }
            except Exception as e:
                self.logger.debug(f"Status check error: {e}")
                return {"connected": False}

        @self.router.get("/containers")
        async def list_containers():
            client = self._get_client()
            if not client:
                raise HTTPException(status_code=503, detail="Docker service unavailable")
            data = []
            for c in client.containers.list(all=True):
                attrs = c.attrs
                state = attrs.get("State", {})
                error = state.get("Error", "")

                data.append(
                    {
                        "id": c.short_id,
                        "name": c.name,
                        "status": c.status,
                        "error": error,
                        "image": attrs.get("Config", {}).get("Image"),
                        "created": attrs.get("Created"),
                        "started_at": state.get("StartedAt"),
                        "command": " ".join(
                            attrs.get("Config", {}).get("Cmd", []) or []
                        ),
                        "ports": attrs.get("NetworkSettings", {}).get("Ports", {}),
                        "networks": list(
                            attrs.get("NetworkSettings", {}).get("Networks", {}).keys()
                        ),
                        "mounts": [
                            {"src": m.get("Source"), "dst": m.get("Destination")}
                            for m in attrs.get("Mounts", [])
                        ],
                        "env": [
                            e
                            for e in attrs.get("Config", {}).get("Env", [])
                            if not any(
                                x in e.lower()
                                for x in ["pass", "key", "secret", "token"]
                            )
                        ],
                    }
                )
            return data

        @self.router.get("/containers/{id}/stats")
        async def get_stats(id: str):
            client = self._get_client()
            if not client:
                raise HTTPException(status_code=503, detail="Docker service unavailable")
            try:
                c = client.containers.get(id)
            except NotFound:
                raise HTTPException(status_code=404, detail="Container not found")

            if c.status != "running":
                return {"cpu": 0.0, "mem": 0, "mem_limit": 0}

            try:
                st = c.stats(stream=False)
                mem_usage = st.get("memory_stats", {}).get("usage", 0)
                mem_limit = st.get("memory_stats", {}).get("limit", 0)

                cpu_delta = (
                    st.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
                    - st.get("precpu_stats", {})
                    .get("cpu_usage", {})
                    .get("total_usage", 0)
                )
                sys_delta = st.get("cpu_stats", {}).get(
                    "system_cpu_usage", 0
                ) - st.get("precpu_stats", {}).get("system_cpu_usage", 0)
                online_cpus = st.get("cpu_stats", {}).get("online_cpus", 1)

                cpu_pct = 0.0
                if sys_delta > 0.0 and cpu_delta > 0.0:
                    cpu_pct = (cpu_delta / sys_delta) * online_cpus * 100.0

                return {
                    "cpu": round(cpu_pct, 2),
                    "mem": mem_usage,
                    "mem_limit": mem_limit,
                }
            except Exception as e:
                return {"cpu": 0.0, "mem": 0, "mem_limit": 0, "error": str(e)}

        @self.router.post("/containers/run")
        async def run_container(payload: Dict[str, Any] = Body(...)):
            client = self._get_client()
            if not client:
                raise HTTPException(status_code=503, detail="Docker service unavailable")
            try:
                mode = payload.get("mode", "basic")
                run_kwargs: Dict[str, Any] = {"detach": True}

                if mode == "advanced":
                    run_kwargs.update(payload.get("config", {}))
                else:
                    image = payload.get("image")
                    if not image:
                        raise ValueError("Image name is required")
                    run_kwargs["image"] = image
                    run_kwargs["name"] = payload.get("name") or None
                    if payload.get("ports") and ":" in payload.get("ports"):
                        h, c = payload.get("ports").split(":", 1)
                        run_kwargs["ports"] = {f"{c}/tcp": int(h)}
                    if payload.get("env"):
                        run_kwargs["environment"] = [
                            e.strip() for e in payload.get("env").split(",") if e.strip()
                        ]
                    if payload.get("restart") and payload.get("restart") != "no":
                        run_kwargs["restart_policy"] = {"Name": payload.get("restart")}
                    if payload.get("volumes") and ":" in payload.get("volumes"):
                        h, c = payload.get("volumes").split(":", 1)
                        run_kwargs["volumes"] = {h: {"bind": c, "mode": "rw"}}

                def do_run(kwargs, task_id):
                    try:
                        client.containers.run(**kwargs)
                    except Exception as e:
                        self.logger.error(f"Container deployment failed ({task_id}): {e}")
                    finally:
                        with self._lock:
                            self._deploying.pop(task_id, None)

                task_id = (
                    payload.get("name") or payload.get("image") or "new-container"
                )
                with self._lock:
                    self._deploying[task_id] = "Launching..."
                threading.Thread(
                    target=do_run, args=(run_kwargs, task_id), daemon=True
                ).start()
                return {"success": True}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @self.router.post("/containers/{id}/{action}")
        async def container_action(id: str, action: str):
            client = self._get_client()
            if not client:
                raise HTTPException(status_code=503, detail="Docker service unavailable")
            try:
                c = client.containers.get(id)
                if action == "start":
                    c.start()
                elif action == "stop":
                    c.stop()
                elif action == "restart":
                    c.restart()
                elif action == "remove":
                    c.remove(force=True)
                else:
                    raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")
                return {"success": True}
            except NotFound:
                raise HTTPException(status_code=404, detail="Container not found")
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/containers/{id}/logs")
        async def get_logs(id: str, tail: int = 500):
            client = self._get_client()
            if not client:
                raise HTTPException(status_code=503, detail="Docker service unavailable")
            try:
                c = client.containers.get(id)
                return {"logs": c.logs(tail=tail).decode("utf-8", errors="ignore")}
            except NotFound:
                raise HTTPException(status_code=404, detail="Container not found")

        @self.router.get("/images")
        async def list_images():
            client = self._get_client()
            if not client:
                raise HTTPException(status_code=503, detail="Docker service unavailable")
            return [
                {"id": i.short_id, "tags": i.tags, "size": i.attrs.get("Size", 0)}
                for i in client.images.list()
            ]

        @self.router.post("/containers/bulk/{action}")
        async def bulk_action(action: str):
            client = self._get_client()
            if not client:
                raise HTTPException(status_code=503, detail="Docker service unavailable")
            for c in client.containers.list(all=True):
                try:
                    if action == "start":
                        c.start()
                    elif action == "stop":
                        c.stop()
                    elif action == "restart":
                        c.restart()
                except Exception:
                    continue
            return {"success": True}

        @self.router.post("/system/prune")
        async def prune_system():
            client = self._get_client()
            if not client:
                raise HTTPException(status_code=503, detail="Docker service unavailable")
            client.containers.prune()
            client.images.prune()
            client.networks.prune()
            client.volumes.prune()
            return {"success": True}

        @self.router.post("/images/pull")
        async def pull_image(image: str = Body(..., embed=True)):
            client = self._get_client()
            if not client:
                raise HTTPException(status_code=503, detail="Docker service unavailable")

            def do_pull(repo):
                with self._lock:
                    self._pulling[repo] = "Pulling..."
                try:
                    client.images.pull(repo)
                except Exception as e:
                    self.logger.error(f"Failed to pull image {repo}: {e}")
                finally:
                    with self._lock:
                        self._pulling.pop(repo, None)

            threading.Thread(target=do_pull, args=(image,), daemon=True).start()
            return {"success": True}

        @self.router.delete("/images/{id}")
        async def delete_image(id: str):
            client = self._get_client()
            if not client:
                raise HTTPException(status_code=503, detail="Docker service unavailable")
            try:
                client.images.remove(id, force=True)
                return {"success": True}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @self.router.get("/networks")
        async def list_networks():
            client = self._get_client()
            if not client:
                raise HTTPException(status_code=503, detail="Docker service unavailable")
            return [
                {"id": n.short_id, "name": n.name, "driver": n.attrs.get("Driver")}
                for n in client.networks.list()
            ]

        @self.router.delete("/networks/{id}")
        async def delete_network(id: str):
            client = self._get_client()
            if not client:
                raise HTTPException(status_code=503, detail="Docker service unavailable")
            try:
                client.networks.get(id).remove()
                return {"success": True}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @self.router.get("/volumes")
        async def list_volumes():
            client = self._get_client()
            if not client:
                raise HTTPException(status_code=503, detail="Docker service unavailable")
            return [
                {
                    "name": v.name,
                    "driver": v.attrs.get("Driver"),
                    "mountpoint": v.attrs.get("Mountpoint"),
                }
                for v in client.volumes.list()
            ]

        @self.router.delete("/volumes/{name}")
        async def delete_volume(name: str):
            client = self._get_client()
            if not client:
                raise HTTPException(status_code=503, detail="Docker service unavailable")
            try:
                client.volumes.get(name).remove(force=True)
                return {"success": True}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

    def initialize(self) -> bool:
        self.logger.info("Vessel Forge v2 worker active.")
        return True

    def cleanup(self):
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass

    def get_routes(self) -> APIRouter:
        return self.router
