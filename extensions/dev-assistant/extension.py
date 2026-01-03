import os
import subprocess
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Body
from typing import List, Dict, Optional
from pclink.core.extension_base import ExtensionBase

class Extension(ExtensionBase):
    def __init__(self, metadata, extension_path, config: dict):
        super().__init__(metadata, extension_path, config)
        self.recent_projects_file = self.extension_path / "recent_projects.json"
        self.working_dir = Path.home()
        self.setup_routes()

    def _load_projects(self) -> List[str]:
        if not self.recent_projects_file.exists():
            return []
        try:
            with open(self.recent_projects_file, "r") as f:
                return json.load(f)
        except:
            return []

    def _save_project(self, path: str):
        projects = self._load_projects()
        if path in projects:
            projects.remove(path)
        projects.insert(0, path)
        projects = projects[:10]  # Keep last 10
        with open(self.recent_projects_file, "w") as f:
            json.dump(projects, f)

    def _is_git(self, path: Path) -> bool:
        return (path / ".git").exists()

    def _get_git_info(self, path: Path) -> Dict:
        if not self._is_git(path):
            return {"is_git": False}
        
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=path, encoding='utf-8', stderr=subprocess.STDOUT
            ).strip()
            
            changes = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=path, encoding='utf-8', stderr=subprocess.STDOUT
            ).strip()
            
            return {
                "is_git": True,
                "branch": branch,
                "has_changes": len(changes) > 0,
                "change_count": len(changes.split('\n')) if changes else 0
            }
        except:
            return {"is_git": True, "error": "Not a git repo or git not found"}

    def _get_available_scripts(self, path: Path) -> List[Dict]:
        scripts = []
        
        # Node.js
        if (path / "package.json").exists():
            try:
                with open(path / "package.json", "r") as f:
                    data = json.load(f)
                    if "scripts" in data:
                        for name in data["scripts"]:
                            scripts.append({"type": "npm", "name": name, "command": f"npm run {name}"})
            except: pass

        # Flutter
        if (path / "pubspec.yaml").exists():
            scripts.append({"type": "flutter", "name": "Get Packages", "command": "flutter pub get"})
            scripts.append({"type": "flutter", "name": "Run Debug", "command": "flutter run"})
            scripts.append({"type": "flutter", "name": "Build APK", "command": "flutter build apk"})

        # Python
        if (path / "requirements.txt").exists():
            scripts.append({"type": "python", "name": "Install Requirements", "command": "pip install -r requirements.txt"})

        return scripts

    def setup_routes(self):
        @self.router.get("/projects")
        async def get_projects():
            return self._load_projects()

        @self.router.post("/scan")
        async def scan_project(data: Dict = Body(...)):
            path = Path(data.get("path", ""))
            if not path.exists() or not path.is_dir():
                raise HTTPException(status_code=400, detail="Invalid project path")
            
            self._save_project(str(path))
            
            return {
                "name": path.name,
                "path": str(path),
                "git": self._get_git_info(path),
                "scripts": self._get_available_scripts(path)
            }

        @self.router.post("/run")
        async def run_command(data: Dict = Body(...)):
            path = data.get("path")
            command = data.get("command")
            
            if not path or not command:
                raise HTTPException(status_code=400, detail="Missing path or command")

            try:
                # Run command and capture last 50 lines of output
                # Use shell=True for complex commands/node scripts
                process = subprocess.Popen(
                    command,
                    cwd=path,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                
                output = []
                # Simple non-blocking capture (read first kilo of output or timeout)
                # In a real app we'd stream this over WS, but for now we'll return a batch
                try:
                    for _ in range(50):
                        line = process.stdout.readline()
                        if not line: break
                        output.append(line.strip())
                except:
                    pass
                
                return {
                    "status": "started",
                    "output": output,
                    "pid": process.pid
                }
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self.router.post("/git/action")
        async def git_action(data: Dict = Body(...)):
            path = data.get("path")
            action = data.get("action")
            
            cmd = ["git", action]
            if action == "pull": cmd = ["git", "pull"]
            elif action == "fetch": cmd = ["git", "fetch"]
            
            try:
                result = subprocess.check_output(
                    cmd, cwd=path, stderr=subprocess.STDOUT, encoding='utf-8'
                )
                return {"status": "success", "output": result}
            except subprocess.CalledProcessError as e:
                return {"status": "error", "output": e.output}

    def initialize(self) -> bool:
        self.logger.info("Dev Assistant Extension initialized.")
        return True

    def cleanup(self):
        self.logger.info("Dev Assistant Extension shutting down.")

    def get_routes(self) -> APIRouter:
        return self.router
