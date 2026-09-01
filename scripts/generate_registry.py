# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 AZHAR ZOUHIR / BYTEDz

import hashlib
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

def get_dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total

def calculate_sha256(file_path: Path) -> Optional[str]:
    if not file_path.exists():
        return None
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def get_dates(path: Path) -> Tuple[str, str]:
    added = None
    updated = None

    try:
        cmd_first = ["git", "log", "--reverse", "--format=%aI", "--", str(path)]
        output_first = subprocess.check_output(cmd_first, text=True, stderr=subprocess.DEVNULL).strip()
        if output_first:
            added = output_first.split("\n")[0]

        cmd_last = ["git", "log", "-1", "--format=%aI", "--", str(path)]
        output_last = subprocess.check_output(cmd_last, text=True, stderr=subprocess.DEVNULL).strip()
        if output_last:
            updated = output_last
    except Exception:
        pass

    if not added:
        added = datetime.fromtimestamp(path.stat().st_ctime).astimezone().isoformat()
    if not updated:
        updated = datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()

    return added, updated

def validate_manifest(data: Dict) -> None:
    required_fields = ["manifest_version", "id", "name", "version"]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required manifest field: '{field}'")

    if data["manifest_version"] != 2:
        raise ValueError(f"Unsupported manifest_version: {data['manifest_version']}. Must be 2.")

def generate_registry() -> None:
    extensions_dir = Path("extensions")
    dist_dir = Path("dist")
    registry: List[Dict] = []

    repo_url = os.environ.get("GITHUB_REPOSITORY", "BYTEDz/pclink-extensions")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    base_raw_url = f"https://raw.githubusercontent.com/{repo_url}/{branch}/extensions"
    release_url = f"https://github.com/{repo_url}/releases/latest/download"

    for ext_folder in sorted(extensions_dir.iterdir()):
        if not ext_folder.is_dir():
            continue

        manifest_path = ext_folder / "manifest.json"
        if not manifest_path.exists():
            continue

        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        validate_manifest(data)

        ext_id = data["id"]
        version = data["version"]

        added_on, updated_on = get_dates(ext_folder)
        file_size = get_dir_size(ext_folder)

        icon_file = data.get("icon", "icon.svg")
        has_icon = (ext_folder / icon_file).exists()

        bundle_name = f"{ext_id}-{version}.pclink"
        bundle_path = dist_dir / bundle_name
        bundle_sha256 = calculate_sha256(bundle_path)

        entry = {
            "id": ext_id,
            "name": data.get("name", ext_id),
            "version": version,
            "description": data.get("description", ""),
            "author": data.get("author", "BYTEDz"),
            "category": data.get("category", "Utility"),
            "supported_platforms": data.get("supported_platforms", ["windows", "linux", "darwin"]),
            "supported_architectures": data.get("supported_architectures", ["x86_64", "amd64", "arm64", "aarch64"]),
            "min_pclink_version": data.get("pclink_version", ">=4.9.0"),
            "min_server_version": data.get("min_server_version", "4.8.0"),
            "theme_aware_icon": data.get("theme_aware_icon", True),
            "icon_url": f"{base_raw_url}/{ext_folder.name}/{icon_file}" if has_icon else None,
            "download_url": f"{release_url}/{bundle_name}",
            "sha256": bundle_sha256,
            "permissions": data.get("permissions", []),
            "declared_permissions": data.get("declared_permissions", data.get("permissions", [])),
            "ui_capabilities": data.get("ui_capabilities", {}),
            "contributes": data.get("contributes", {}),
            "backend": data.get("backend", {"runtime": "none"}),
            "added_on": added_on,
            "updated_on": updated_on,
            "file_size": file_size,
        }

        registry.append(entry)
        print(f"Indexed {ext_id} v{version} (SHA-256: {bundle_sha256[:12] if bundle_sha256 else 'N/A'})")

    with open("extensions.json", "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)

    print(f"Successfully generated extensions.json with {len(registry)} packages.")

if __name__ == "__main__":
    generate_registry()