import os
import json
import yaml
import subprocess
from pathlib import Path
from datetime import datetime

def get_dir_size(path):
    total = 0
    for p in path.rglob('*'):
        if p.is_file():
            total += p.stat().st_size
    return total

def get_dates(path):
    added = None
    updated = None
    
    try:
        # First commit involving this path (Added)
        cmd_first = ['git', 'log', '--reverse', '--format=%aI', '--', str(path)]
        output = subprocess.check_output(cmd_first, text=True, stderr=subprocess.DEVNULL).strip()
        if output:
            added = output.split('\n')[0]

        # Last commit involving this path (Updated)
        cmd_last = ['git', 'log', '-1', '--format=%aI', '--', str(path)]
        output = subprocess.check_output(cmd_last, text=True, stderr=subprocess.DEVNULL).strip()
        if output:
            updated = output
            
    except Exception:
        pass

    # Fallback/Default
    if not added:
        # timestamp to iso 8601
        added = datetime.fromtimestamp(path.stat().st_ctime).astimezone().isoformat()
    if not updated:
        updated = datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()
        
    return added, updated

def generate_registry():
    extensions_dir = Path("extensions")
    registry = []
    
    # Base URL for raw content on GitHub
    repo_url = os.environ.get("GITHUB_REPOSITORY", "BYTEDz/pclink-extensions")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    base_raw_url = f"https://raw.githubusercontent.com/{repo_url}/{branch}/extensions"
    release_url = f"https://github.com/{repo_url}/releases/latest/download"

    for ext_folder in extensions_dir.iterdir():
        if not ext_folder.is_dir():
            continue
            
        manifest_path = ext_folder / "extension.yaml"
        if not manifest_path.exists():
            continue
            
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            
        ext_id = data.get("name")
        version = data.get("version")
        
        added_on, updated_on = get_dates(ext_folder)
        file_size = get_dir_size(ext_folder)

        # Build registry entry
        entry = {
            "id": ext_id,
            "name": data.get("display_name"),
            "version": version,
            "description": data.get("description"),
            "author": data.get("author"),
            "category": data.get("category", "Utility"),
            "supported_platforms": data.get("supported_platforms", ["windows"]),
            "min_pclink_version": data.get("pclink_version", ">=3.1.0"),
            "min_server_version": data.get("min_server_version", "1.0.0"),
            "theme_aware_icon": data.get("theme_aware_icon", False),
            "icon_url": f"{base_raw_url}/{ext_folder.name}/{data.get('icon', 'icon.png')}" if data.get('icon') else None,
            "download_url": f"{release_url}/{ext_id}-{version}.zip",
            "permissions": data.get("permissions", []),
            "added_on": added_on,
            "updated_on": updated_on,
            "file_size": file_size
        }
        
        registry.append(entry)
        print(f"Added {ext_id} v{version} to registry")

    with open("extensions.json", "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
    
    print(f"Successfully generated extensions.json with {len(registry)} entries")

if __name__ == "__main__":
    generate_registry()
