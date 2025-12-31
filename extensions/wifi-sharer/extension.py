import subprocess
import re
from pathlib import Path
from fastapi import APIRouter

from pclink.core.extension_base import ExtensionBase

class Extension(ExtensionBase):
    def __init__(self, metadata, extension_path, config: dict):
        super().__init__(metadata, extension_path, config)
        self.setup_routes()

    def setup_routes(self):
        @self.router.get("/info")
        async def get_wifi_info():
            return self._get_current_wifi_details()

    def _get_current_wifi_details(self):
        try:
            # Helper to run command with proper encoding
            def run_netsh(args):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
                try:
                    # Try using system default encoding (often cp1252 or cp850 on Windows)
                    return subprocess.check_output(
                        args, 
                        startupinfo=startupinfo,
                        stderr=subprocess.STDOUT
                    ).decode(errors="ignore")
                except subprocess.CalledProcessError as e:
                    output = e.output.decode(errors='ignore')
                    # Check for specific service errors
                    if "Wireless AutoConfig Service" in output or "wlansvc" in output:
                        raise Exception("WLAN_SERVICE_NOT_RUNNING")
                    raise Exception(f"Command failed (Exit {e.returncode}): {output}")

            # 1. Get current SSID
            # Command: netsh wlan show interfaces
            output = run_netsh(["netsh", "wlan", "show", "interfaces"])
            
            # Check if functionality is available
            if "There is no wireless interface" in output:
                return {
                    "error": "No WiFi adapter found",
                    "help": "This PC doesn't have a WiFi adapter or it's disabled in Device Manager.",
                    "solution": "This extension only works on devices with WiFi capability"
                }
                
            ssid_match = re.search(r"^\s*SSID\s*:\s*(.*)$", output, re.MULTILINE)
            if not ssid_match:
                return {
                    "error": "Not connected to WiFi",
                    "help": "You're not currently connected to any WiFi network.",
                    "solution": "Connect to a WiFi network first, then try again"
                }
            
            ssid = ssid_match.group(1).strip()
            
            # 2. Get Password just for that SSID
            # Command: netsh wlan show profile name="SSID" key=clear
            profile_output = run_netsh(["netsh", "wlan", "show", "profile", f"name={ssid}", "key=clear"])
            
            # Look for "Key Content"
            pass_match = re.search(r"^\s*Key Content\s*:\s*(.*)$", profile_output, re.MULTILINE)
            password = pass_match.group(1).strip() if pass_match else None
            
            if not password:
                return {
                    "error": "Password not available",
                    "help": "The WiFi password couldn't be retrieved. This might be an open network or the password isn't stored.",
                    "solution": "Check your WiFi settings"
                }
            
            # Authentication type
            auth_match = re.search(r"^\s*Authentication\s*:\s*(.*)$", profile_output, re.MULTILINE)
            auth = auth_match.group(1).strip() if auth_match else "WPA"

            return {
                "ssid": ssid,
                "password": password,
                "auth": auth
            }
        except Exception as e:
            error_msg = str(e)
            
            # Provide helpful guidance for common errors
            if error_msg == "WLAN_SERVICE_NOT_RUNNING":
                self.logger.warning("WLAN AutoConfig service is not running")
                return {
                    "error": "WiFi service not running",
                    "help": "The Windows WLAN AutoConfig service is not running. This usually means WiFi is disabled or you're using Ethernet only.",
                    "solution": "Enable WiFi in Windows Settings → Network & Internet → WiFi"
                }
            else:
                self.logger.error(f"WiFi Sharer error: {error_msg}")
                return {"error": f"Unexpected error: {error_msg}"}

    def initialize(self) -> bool:
        self.logger.info("WiFi Sharer Extension initialized.")
        return True

    def cleanup(self):
        pass

    def get_routes(self) -> APIRouter:
        return self.router
