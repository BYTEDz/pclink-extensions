import os
import json
import yaml
from pathlib import Path

def generate_registry():
    extensions_dir = Path("extensions")
    registry = []
    
    # Base URL for raw content on GitHub
    # Note: User will need to update this or we can make it dynamic via environment variables
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
        
        # Build registry entry
        entry = {
            "id": ext_id,
            "name": data.get("display_name"),
            "version": version,
            "description": data.get("description"),
            "author": data.get("author"),
            "supported_platforms": data.get("supported_platforms", ["windows"]),
            "min_pclink_version": data.get("pclink_version", ">=3.1.0"),
            "icon_url": f"{base_raw_url}/{ext_folder.name}/{data.get('icon', 'icon.png')}" if data.get('icon') else None,
            "download_url": f"{release_url}/{ext_id}-{version}.zip"
        }
        
        registry.append(entry)
        print(f"Added {ext_id} v{version} to registry")

    with open("extensions.json", "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
    
    print(f"Successfully generated extensions.json with {len(registry)} entries")

if __name__ == "__main__":
    generate_registry()
