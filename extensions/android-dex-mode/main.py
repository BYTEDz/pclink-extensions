import asyncio
import logging
from pathlib import Path
from typing import Any, Dict

try:
    from pclink.core.extension_base import ExtensionBase, ExtensionMetadata
except ImportError:
    try:
        from core.extension_base import ExtensionBase, ExtensionMetadata
    except ImportError:
        class ExtensionBase:
            def __init__(self, metadata, extension_path, config, context=None):
                self.metadata = metadata
                self.extension_path = extension_path
                self.config = config
                self.context = context

try:
    from .adb_service import AdbService
    from .binary_manager import BinaryManager
    from .router import create_workspace_router
    from .workspace_service import WorkspaceService
except (ImportError, ValueError):
    from adb_service import AdbService
    from binary_manager import BinaryManager
    from router import create_workspace_router
    from workspace_service import WorkspaceService

log = logging.getLogger(__name__)


class AndroidDexModeExtension(ExtensionBase):
    def __init__(
        self,
        metadata: Any,
        extension_path: Path,
        config: Dict[str, Any],
        context: Any = None,
    ):
        super().__init__(metadata, extension_path, config, context)

        ext_id = getattr(metadata, "id", "android-dex-mode")
        data_dir = getattr(context, "data_path", None)
        if not data_dir:
            try:
                from pclink.core.constants import APP_DATA_PATH
            except ImportError:
                try:
                    from core.constants import APP_DATA_PATH
                except ImportError:
                    APP_DATA_PATH = Path.home() / ".config" / "PCLink"
            data_dir = APP_DATA_PATH / "extension_data" / ext_id

        self.bin_manager = BinaryManager(data_dir)
        self.adb_service = AdbService(self.bin_manager.resolve_adb_path)
        self.workspace_service = WorkspaceService(self.bin_manager, self.adb_service)
        self.router = create_workspace_router(
            self.workspace_service,
            self.bin_manager,
            self.adb_service,
            self.context,
        )

    def initialize(self) -> bool:
        name = getattr(self.metadata, "name", "Android DeX Mode")
        version = getattr(self.metadata, "version", "1.0.0")
        log.info(f"Initializing extension '{name}' (v{version})")
        status = self.bin_manager.check_binaries()
        log.info(f"Subsystem binaries resolved: {status}")
        return True

    def cleanup(self) -> None:
        log.info("Cleaning up Android DeX Mode resources...")
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.workspace_service.stop_workspace())
            else:
                asyncio.run(self.workspace_service.stop_workspace())
        except Exception as e:
            log.warning(f"Error executing DeX workspace cleanup routine: {e}")

    def get_routes(self):
        return self.router
