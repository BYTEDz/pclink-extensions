# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 AZHAR ZOUHIR / BYTEDz

import json
import sys
from pathlib import Path
from typing import List

REQUIRED_MANIFEST_FIELDS = [
    "manifest_version",
    "id",
    "name",
    "version",
    "min_server_version",
    "pclink_version",
    "category",
]

VALID_CATEGORIES = {
    "Utility",
    "Media",
    "Security",
    "Productivity",
    "System",
    "Developer",
}

VALID_RUNTIMES = {"none", "python", "binary", "node"}

def lint_extension(ext_dir: Path) -> List[str]:
    errors = []
    manifest_path = ext_dir / "manifest.json"

    if not manifest_path.exists():
        return [f"Missing manifest.json in {ext_dir.name}"]

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [f"Invalid JSON in {manifest_path}: {e}"]

    # 1. Schema and Version Validation
    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in data:
            errors.append(f"Missing required field '{field}' in manifest")

    if data.get("manifest_version") != 2:
        errors.append(f"manifest_version must be 2, got {data.get('manifest_version')}")

    if data.get("id") != ext_dir.name:
        errors.append(f"Manifest id '{data.get('id')}' does not match directory name '{ext_dir.name}'")

    if data.get("min_server_version") != "4.8.0":
        errors.append(f"min_server_version must be '4.8.0', got '{data.get('min_server_version')}'")

    if data.get("pclink_version") != ">=4.9.0":
        errors.append(f"pclink_version must be '>=4.9.0', got '{data.get('pclink_version')}'")

    if "enabled" in data:
        errors.append("Redundant 'enabled' field present in manifest. Runtime state belongs to host server.")

    if data.get("category") not in VALID_CATEGORIES:
        errors.append(f"Invalid category '{data.get('category')}'. Must be one of: {VALID_CATEGORIES}")

    # 2. Backend Validation
    backend = data.get("backend", {})
    runtime = backend.get("runtime", "none")
    if runtime not in VALID_RUNTIMES:
        errors.append(f"Invalid backend runtime '{runtime}'. Must be one of: {VALID_RUNTIMES}")

    if runtime == "python":
        entry_point = backend.get("entry_point", "")
        file_part = entry_point.split(":", 1)[0] if ":" in entry_point else entry_point
        if not (ext_dir / file_part).exists():
            errors.append(f"Python backend entry file '{file_part}' does not exist on disk")

    # 3. Contributions Validation
    contributes = data.get("contributes", {})
    for view in contributes.get("views", []):
        entry = view.get("entry_point")
        if entry and not (ext_dir / entry).exists():
            errors.append(f"View entry point '{entry}' does not exist on disk")

    for widget in contributes.get("dashboard_widgets", []):
        entry = widget.get("entry_point")
        if entry and not (ext_dir / entry).exists():
            errors.append(f"Widget entry point '{entry}' does not exist on disk")

    # 4. Icon Validation
    icon = data.get("icon")
    if icon and not (ext_dir / icon).exists():
        errors.append(f"Icon file '{icon}' does not exist on disk")

    return errors

def main() -> int:
    extensions_dir = Path("extensions")
    if not extensions_dir.exists():
        print("Error: 'extensions' directory not found.")
        return 1

    total_errors = 0
    total_checked = 0

    for ext_folder in sorted(extensions_dir.iterdir()):
        if not ext_folder.is_dir():
            continue

        total_checked += 1
        issues = lint_extension(ext_folder)
        if issues:
            total_errors += len(issues)
            print(f"FAILED: {ext_folder.name}")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print(f"PASSED: {ext_folder.name}")

    print(f"\nLint complete: {total_checked} extensions verified, {total_errors} errors found.")
    return 1 if total_errors > 0 else 0

if __name__ == "__main__":
    sys.exit(main())