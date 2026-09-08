import logging
from typing import Any, Dict
from fastapi import APIRouter, HTTPException

log = logging.getLogger(__name__)


def _to_dict(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    if hasattr(payload, "dict"):
        return payload.dict()
    return {}


def create_workspace_router(workspace_service, binary_manager, adb_service, context) -> APIRouter:
    router = APIRouter()

    @router.get("/status")
    async def get_workspace_status():
        return workspace_service.get_status()

    @router.get("/binaries/check")
    async def check_binaries():
        return binary_manager.check_binaries()

    @router.post("/binaries/download")
    async def download_binaries():
        success, msg = await binary_manager.ensure_binaries()
        if not success:
            raise HTTPException(status_code=500, detail=msg)
        return {"success": True, "message": msg}

    @router.get("/devices")
    async def get_discovered_devices():
        connected_list = []
        try:
            try:
                from pclink.core.device_manager import device_manager
            except ImportError:
                from core.device_manager import device_manager

            devices = device_manager.get_approved_devices()
            for d in devices:
                if d.current_ip:
                    connected_list.append({
                        "id": d.device_id,
                        "name": d.device_name,
                        "ip": d.current_ip,
                        "platform": d.platform,
                    })
        except Exception as e:
            log.debug(f"Could not fetch device list from DeviceManager directly: {e}")

        return {"devices": connected_list}

    @router.post("/connect")
    async def connect_adb(payload: Any = None):
        data = _to_dict(payload)
        ip = str(data.get("ip", "")).strip()
        port = int(data.get("port", 5555))

        if not ip:
            raise HTTPException(status_code=400, detail="Target IP address is required.")

        connected, msg = await adb_service.connect(ip, port)
        if not connected:
            raise HTTPException(status_code=400, detail=msg)
        return {"success": True, "message": msg}

    @router.post("/pair")
    async def pair_adb(payload: Any = None):
        data = _to_dict(payload)
        ip = str(data.get("ip", "")).strip()
        port = int(data.get("port", 0))
        code = str(data.get("code", "")).strip()

        if not ip or not port or not code:
            raise HTTPException(status_code=400, detail="IP, port, and pairing code are required.")

        paired, msg = await adb_service.pair(ip, port, code)
        if not paired:
            raise HTTPException(status_code=400, detail=msg)
        return {"success": True, "message": msg}

    @router.post("/settings/open-wireless-debugging")
    async def open_wireless_debugging_screen(payload: Any = None):
        data = _to_dict(payload)
        ip = str(data.get("ip", "")).strip()
        port = int(data.get("port", 5555))
        target = f"{ip}:{port}" if ip else None
        success, msg = await adb_service.open_wireless_debugging_settings(target)
        if not success:
            raise HTTPException(status_code=400, detail=msg)
        return {"success": True, "message": msg}

    @router.post("/start")
    async def start_session(payload: Any = None):
        data = _to_dict(payload)
        ip = str(data.get("ip", "")).strip()
        port = int(data.get("port", 5555))
        width = int(data.get("width", 1920))
        height = int(data.get("height", 1080))
        dpi = int(data.get("dpi", 210))
        bitrate_mbps = int(data.get("bitrate_mbps", 16))
        max_fps = int(data.get("max_fps", 60))

        if not ip:
            raise HTTPException(status_code=400, detail="Target IP address is required.")

        try:
            return await workspace_service.start_workspace(
                ip=ip,
                port=port,
                width=width,
                height=height,
                dpi=dpi,
                bitrate_mbps=bitrate_mbps,
                max_fps=max_fps,
            )
        except Exception as e:
            log.error(f"Failed to start desktop workspace: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/stop")
    async def stop_session():
        return await workspace_service.stop_workspace()

    @router.get("/apps")
    async def list_workspace_apps():
        return {"apps": await workspace_service.list_applications()}

    @router.post("/apps/launch")
    async def launch_app(payload: Any = None):
        data = _to_dict(payload)
        package_name = str(data.get("package_name", "")).strip()
        if not package_name:
            raise HTTPException(status_code=400, detail="Package name is required.")

        try:
            return await workspace_service.launch_application(package_name)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router
