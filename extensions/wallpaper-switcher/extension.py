import base64
import io
import os
import platform
import subprocess
import tempfile
import urllib.request
from pclink.core.extension_base import ExtensionBase
from fastapi import APIRouter
from fastapi.responses import Response

SYSTEM = platform.system()

def set_wallpaper_windows(path):
    import ctypes
    ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 3)

def set_wallpaper_darwin(path):
    script = f'''
    tell application "System Events"
        tell every desktop
            set picture to "{path}"
        end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", script], check=True)

def set_wallpaper_linux(path):
    uri = path.replace("file://", "")
    for cmd in [
        ["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", f"file://{uri}"],
        ["gsettings", "set", "org.gnome.desktop.background", "picture-uri", f"file://{uri}"],
        ["gsettings", "set", "org.mate.background", "picture-filename", uri],
        ["xfconf-query", "-c", "xfce4-desktop", "-p", "/backdrop/screen0/monitor0/image-path", "-s", uri],
        ["feh", "--bg-scale", uri],
    ]:
        try:
            subprocess.run(cmd, capture_output=True, timeout=5)
        except Exception:
            continue

SET_WALLPAPER = {
    "Windows": set_wallpaper_windows,
    "Darwin": set_wallpaper_darwin,
    "Linux": set_wallpaper_linux,
}.get(SYSTEM, lambda p: None)

BUILTIN_WALLPAPERS = [
    {"name": "Sunset Gradient", "colors": ["#ff7e5f", "#feb47b"], "style": "linear-gradient(135deg, #ff7e5f, #feb47b)"},
    {"name": "Ocean Blue", "colors": ["#2193b0", "#6dd5ed"], "style": "linear-gradient(135deg, #2193b0, #6dd5ed)"},
    {"name": "Midnight", "colors": ["#0f0c29", "#302b63", "#24243e"], "style": "linear-gradient(135deg, #0f0c29, #302b63, #24243e)"},
    {"name": "Aurora", "colors": ["#00b09b", "#96c93d"], "style": "linear-gradient(135deg, #00b09b, #96c93d)"},
    {"name": "Nordic", "colors": ["#2c3e50", "#3498db"], "style": "linear-gradient(135deg, #2c3e50, #3498db)"},
    {"name": "Sunset Rose", "colors": ["#ff6b6b", "#c56cf0"], "style": "linear-gradient(135deg, #ff6b6b, #c56cf0)"},
    {"name": "Amber Glow", "colors": ["#f7971e", "#ffd200"], "style": "linear-gradient(135deg, #f7971e, #ffd200)"},
    {"name": "Deep Space", "colors": ["#000000", "#434343"], "style": "linear-gradient(135deg, #000000, #434343)"},
]

def generate_gradient_png(colors, width=1920, height=1080):
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (width, height), colors[0] if len(colors) == 1 else None)
        if len(colors) > 1:
            draw = ImageDraw.Draw(img)
            n = len(colors) - 1
            for i in range(n):
                y0 = int(height * i / n)
                y1 = int(height * (i + 1) / n)
                for y in range(y0, y1):
                    ratio = (y - y0) / (y1 - y0)
                    r = int(int(colors[i][1:3], 16) * (1 - ratio) + int(colors[i + 1][1:3], 16) * ratio)
                    g = int(int(colors[i][3:5], 16) * (1 - ratio) + int(colors[i + 1][3:5], 16) * ratio)
                    b = int(int(colors[i][5:7], 16) * (1 - ratio) + int(colors[i + 1][5:7], 16) * ratio)
                    draw.line([(0, y), (width, y)], fill=(r, g, b))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        return None


class Extension(ExtensionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_routes()

    def setup_routes(self):
        @self.router.get("/builtins")
        async def get_builtins():
            return {"wallpapers": BUILTIN_WALLPAPERS}

        @self.router.post("/set-builtin")
        async def set_builtin(data: dict):
            index = data.get("index", 0)
            if index < 0 or index >= len(BUILTIN_WALLPAPERS):
                return {"success": False, "error": "Invalid index"}
            wp = BUILTIN_WALLPAPERS[index]
            png_data = generate_gradient_png(wp["colors"])
            if png_data is None:
                return {"success": False, "error": "PIL not available for gradient generation"}
            path = os.path.join(tempfile.gettempdir(), "pclink-wallpaper.png")
            with open(path, "wb") as f:
                f.write(png_data)
            SET_WALLPAPER(path)
            return {"success": True, "name": wp["name"], "path": path}

        @self.router.post("/set-image")
        async def set_image(data: dict):
            b64 = data.get("image", "")
            img_bytes = base64.b64decode(b64)
            path = os.path.join(tempfile.gettempdir(), "pclink-wallpaper-user.png")
            with open(path, "wb") as f:
                f.write(img_bytes)
            SET_WALLPAPER(path)
            return {"success": True, "path": path}

        @self.router.post("/set-url")
        async def set_from_url(data: dict):
            url = data.get("url", "")
            path = os.path.join(tempfile.gettempdir(), "pclink-wallpaper-url.png")
            urllib.request.urlretrieve(url, path)
            SET_WALLPAPER(path)
            return {"success": True, "path": path}

        @self.router.get("/current")
        async def get_current():
            if SYSTEM == "Windows":
                import ctypes
                path = ctypes.create_unicode_buffer(512)
                ctypes.windll.user32.SystemParametersInfoW(0x73, 512, path, 0)
                return {"path": path.value}
            elif SYSTEM == "Linux":
                try:
                    result = subprocess.run(
                        ["gsettings", "get", "org.gnome.desktop.background", "picture-uri"],
                        capture_output=True, text=True, timeout=5
                    )
                    return {"path": result.stdout.strip().strip("'")}
                except Exception:
                    pass
            return {"path": "Unknown"}

    def initialize(self) -> bool:
        return True

    def cleanup(self):
        pass

    def get_routes(self) -> APIRouter:
        return self.router

