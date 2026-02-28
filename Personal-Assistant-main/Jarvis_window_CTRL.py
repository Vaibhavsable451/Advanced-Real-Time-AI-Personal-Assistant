import os
import sys
import asyncio
import shutil
import webbrowser
import ctypes
from pathlib import Path
from typing import Optional, Dict, Any, List

# LiveKit decorator (safe import)
from livekit.agents import function_tool

# Optional psutil import for battery info
try:
    import psutil
except Exception:
    psutil = None

# Optional OpenCV for camera
try:
    import cv2
except Exception:
    cv2 = None

import socket
import platform
try:
    import pyautogui
except Exception:
    pyautogui = None

# ---------------------------------------------
# Helper: Run commands asynchronously
# ---------------------------------------------
async def _run_async(cmd: List[str]) -> Dict[str, Any]:
    """Run a subprocess command and return a dict with stdout/stderr/returncode."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return {
            "returncode": proc.returncode,
            "stdout": out.decode(errors="ignore").strip(),
            "stderr": err.decode(errors="ignore").strip(),
        }
    except Exception as e:
        return {"returncode": -1, "error": str(e)}

# ---------------------------------------------
# Core Windows control tools
# ---------------------------------------------

@function_tool
async def shutdown_system(force: bool = False) -> Dict[str, Any]:
    """Shut down the computer immediately. Use force=True to force-close apps."""
    try:
        cmd = ["shutdown", "/s", "/t", "0"]
        if force:
            cmd.append("/f")
        # Start the shutdown command and return immediately
        await _run_async(cmd)
        return {"ok": True, "action": "shutdown", "cmd": " ".join(cmd)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@function_tool
async def restart_system(force: bool = False) -> Dict[str, Any]:
    """Restart the computer immediately."""
    try:
        cmd = ["shutdown", "/r", "/t", "0"]
        if force:
            cmd.append("/f")
        await _run_async(cmd)
        return {"ok": True, "action": "restart", "cmd": " ".join(cmd)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@function_tool
async def cancel_shutdown() -> Dict[str, Any]:
    """Cancel a pending system shutdown (shutdown /a)."""
    try:
        res = await _run_async(["shutdown", "/a"])
        if res.get("returncode") == 0:
            return {"ok": True, "action": "cancel_shutdown"}
        # sometimes /a returns non-zero when no shutdown pending; still return stderr
        return {"ok": False, "error": res.get("stderr") or res.get("stdout")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@function_tool
async def sleep_system() -> Dict[str, Any]:
    """Put the computer to sleep. Uses native API when possible, otherwise falls back."""
    try:
        # Try calling powrprof.SetSuspendState through ctypes (requires appropriate privileges)
        try:
            powr = ctypes.WinDLL("PowrProf")
            # BOOL SetSuspendState(BOOL Hibernate, BOOL ForceCritical, BOOL DisableWakeEvent);
            # We want sleep (hibernate=False), ForceCritical=False, DisableWakeEvent=False
            rc = powr.SetSuspendState(False, False, False)
            # If call succeeded, rc may be non-zero
            return {"ok": True, "action": "sleep", "rc": bool(rc)}
        except Exception:
            # fallback to the previous approach (rundll32) in a thread to avoid blocking
            await asyncio.to_thread(os.system, "rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            return {"ok": True, "action": "sleep", "fallback": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ---------------------------------------------
# Lock screen
# ---------------------------------------------

@function_tool
async def lock_screen() -> Dict[str, Any]:
    """Lock the Windows session immediately."""
    try:
        # Use user32 LockWorkStation
        ctypes.windll.user32.LockWorkStation()
        return {"ok": True, "action": "lock_screen"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ---------------------------------------------
# Folder & file management
# ---------------------------------------------

@function_tool
async def create_folder(path: Optional[str] = None) -> Dict[str, Any]:
    """Create a new folder."""
    try:
        if not path:
            path = str(Path.home() / "NewFolder_Jarvis")
        p = Path(path)
        await asyncio.to_thread(p.mkdir, parents=True, exist_ok=True)
        return {"ok": True, "path": str(p.resolve())}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@function_tool
async def list_folder_items(path: Optional[str] = None) -> Dict[str, Any]:
    """List items inside a folder."""
    try:
        if not path:
            path = os.getcwd()
        p = Path(path)
        if not p.exists() or not p.is_dir():
            return {"ok": False, "error": "Invalid directory"}
        items = await asyncio.to_thread(lambda: [c.name for c in p.iterdir()])
        return {"ok": True, "path": str(p), "items": items}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@function_tool
async def open_file(path: Optional[str] = None) -> Dict[str, Any]:
    """Open a file or folder. If no path provided, open user's Documents folder."""
    try:
        if not path:
            default = Path.home() / "Documents"
            await asyncio.to_thread(os.startfile, str(default))
            return {"ok": True, "opened": str(default)}

        p = Path(path)
        if not p.exists():
            return {"ok": False, "error": f"Path not found: {path}"}

        # If it's a folder - open in Explorer
        if p.is_dir():
            await asyncio.to_thread(os.startfile, str(p))
            return {"ok": True, "opened": str(p)}

        # If it's a file - open with default application
        await asyncio.to_thread(os.startfile, str(p))
        return {"ok": True, "opened": str(p)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@function_tool
async def open_pdf_in_folder(folder: Optional[str] = None) -> Dict[str, Any]:
    """Find the first PDF in a folder and open it. If no folder provided, search Documents."""
    try:
        folder = folder or str(Path.home() / "Documents")
        p = Path(folder)
        if not p.exists() or not p.is_dir():
            return {"ok": False, "error": "Invalid folder"}
        pdfs = list(p.rglob("*.pdf"))
        if not pdfs:
            return {"ok": False, "error": "No PDF files found"}
        await asyncio.to_thread(os.startfile, str(pdfs[0]))
        return {"ok": True, "opened": str(pdfs[0])}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ---------------------------------------------
# Run application / media (improved)
# ---------------------------------------------

@function_tool
async def run_application_or_media(app_name_or_path: Optional[str] = None,
                                   folder: Optional[str] = None) -> Dict[str, Any]:
    """Run a given application or play media if found."""
    try:
        if app_name_or_path:
            exe = shutil.which(app_name_or_path)
            if exe:
                # use create_subprocess_exec so we don't block
                try:
                    await asyncio.create_subprocess_exec(exe)
                except Exception:
                    # fallback to startfile
                    await asyncio.to_thread(os.startfile, exe)
                return {"ok": True, "ran": exe}
            path = Path(app_name_or_path)
            if path.exists():
                await asyncio.to_thread(os.startfile, str(path))
                return {"ok": True, "opened": str(path)}
        folder = folder or str(Path.home() / "Videos")
        for ext in ("*.mp4", "*.mp3", "*.mkv"):
            files = list(Path(folder).glob(ext))
            if files:
                await asyncio.to_thread(os.startfile, str(files[0]))
                return {"ok": True, "opened": str(files[0])}
        return {"ok": False, "error": "No file or app found"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ---------------------------------------------
# System Information
# ---------------------------------------------

@function_tool
async def get_battery_info() -> Dict[str, Any]:
    """Return battery info."""
    if not psutil:
        return {"ok": False, "error": "psutil not installed"}
    try:
        battery = psutil.sensors_battery()
        if not battery:
            return {"ok": False, "error": "No battery detected"}
        return {"ok": True, "percent": battery.percent, "plugged_in": battery.power_plugged}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@function_tool
async def wifi_status() -> Dict[str, Any]:
    """Check Wi-Fi status."""
    res = await _run_async(["netsh", "wlan", "show", "interfaces"])
    return {"ok": True, "output": res.get("stdout")}


@function_tool
async def bluetooth_status() -> Dict[str, Any]:
    """Check Bluetooth devices."""
    res = await _run_async(["powershell", "-Command", "Get-PnpDevice -Class Bluetooth"])
    return {"ok": True, "output": res.get("stdout")}


@function_tool
async def get_resource_usage() -> Dict[str, Any]:
    """Get detailed CPU, RAM, and Disk usage information."""
    if not psutil:
        return {"ok": False, "error": "psutil not installed"}
    try:
        cpu_pct = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "ok": True,
            "cpu_usage_percent": cpu_pct,
            "ram_total_gb": round(mem.total / (1024**3), 2),
            "ram_used_gb": round(mem.used / (1024**3), 2),
            "ram_usage_percent": mem.percent,
            "disk_total_gb": round(disk.total / (1024**3), 2),
            "disk_used_gb": round(disk.used / (1024**3), 2),
            "disk_free_gb": round(disk.free / (1024**3), 2),
            "disk_usage_percent": disk.percent
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@function_tool
async def get_network_details() -> Dict[str, Any]:
    """Get local IP, hostname, and operating system details."""
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        os_info = platform.platform()
        
        return {
            "ok": True,
            "hostname": hostname,
            "local_ip": local_ip,
            "os": os_info,
            "architecture": platform.architecture()[0]
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@function_tool
async def kill_process(process_name: str) -> Dict[str, Any]:
    """Kill a running process by its name (e.g., 'chrome.exe', 'notepad')."""
    if not psutil:
        return {"ok": False, "error": "psutil not installed"}
    try:
        count = 0
        for proc in psutil.process_iter(['name']):
            if process_name.lower() in proc.info['name'].lower():
                proc.kill()
                count += 1
        
        if count > 0:
            return {"ok": True, "message": f"Terminated {count} instances of {process_name}"}
        return {"ok": False, "error": f"No process named {process_name} found"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@function_tool
async def empty_recycle_bin() -> Dict[str, Any]:
    """Empty the Windows Recycle Bin."""
    try:
        # SHEmptyRecycleBinW constant for silent operation: 1 (no confirmation), 2 (no progress), 4 (no sound)
        # We'll use 1 | 2 | 4 = 7
        ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)
        return {"ok": True, "message": "Recycle bin emptied successfully."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@function_tool
async def take_screenshot(filename: Optional[str] = None) -> Dict[str, Any]:
    """Take a full screenshot and save it to the Pictures folder."""
    if not pyautogui:
        return {"ok": False, "error": "pyautogui not installed"}
    try:
        save_dir = Path.home() / "Pictures" / "JarvisScreenshots"
        save_dir.mkdir(parents=True, exist_ok=True)
        if not filename:
            filename = f"screenshot_{int(asyncio.get_event_loop().time() * 1000)}.png"
        save_path = save_dir / filename
        
        screenshot = await asyncio.to_thread(pyautogui.screenshot)
        await asyncio.to_thread(screenshot.save, str(save_path))
        
        return {"ok": True, "path": str(save_path), "message": "Screenshot saved."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ---------------------------------------------
# Open common applications and websites
# ---------------------------------------------

@function_tool
async def open_quick_settings(section: Optional[str] = None) -> Dict[str, Any]:
    """Open Windows Settings."""
    uri = f"ms-settings:{section or ''}"
    await asyncio.to_thread(os.system, f"start {uri}")
    return {"ok": True, "opened": uri}


@function_tool
async def open_system_info() -> Dict[str, Any]:
    """Open Windows system info panel."""
    await asyncio.to_thread(os.system, "msinfo32")
    return {"ok": True, "action": "opened_system_info"}


@function_tool
async def open_common_app(app: str, query: Optional[str] = None) -> Dict[str, Any]:
    """
    Open common apps or websites:
    Supported: chrome, youtube, chatgpt, gemini, whatsapp, google, etc.
    Added aliases for easy voice recognition.
    """
    app_low = app.lower().strip()
    try:
        if app_low == "chrome":
            try:
                await asyncio.to_thread(os.startfile, "chrome")
                return {"ok": True, "opened": "Google Chrome"}
            except Exception:
                webbrowser.open("https://www.google.com")
                return {"ok": True, "opened": "Google Chrome (Browser Fallback)"}

        elif app_low in ("youtube", "yt"):
            webbrowser.open("https://www.youtube.com")
            return {"ok": True, "opened": "YouTube"}

        elif app_low in ("chatgpt", "chat gpt", "gpt"):
            webbrowser.open("https://chatgpt.com/")
            return {"ok": True, "opened": "ChatGPT"}

        elif app_low in ("gemini", "google gemini", "google ai", "ai"):
            webbrowser.open("https://gemini.google.com/")
            return {"ok": True, "opened": "Google Gemini"}

        elif app_low == "notepad":
            await asyncio.to_thread(os.startfile, "notepad.exe")
            return {"ok": True, "opened": "Notepad"}

        elif app_low in ("vscode", "vs code", "code"):
            try:
                await asyncio.to_thread(os.startfile, "code")
                return {"ok": True, "opened": "Visual Studio Code"}
            except Exception:
                return {"ok": False, "error": "VS Code not found in PATH"}

        elif app_low == "cursor":
            try:
                await asyncio.to_thread(os.startfile, "cursor")
                return {"ok": True, "opened": "Cursor Editor"}
            except Exception:
                return {"ok": False, "error": "Cursor not found in PATH"}

        elif app_low == "whatsapp":
            webbrowser.open("https://web.whatsapp.com/")
            return {"ok": True, "opened": "WhatsApp Web"}

        elif app_low in ("google", "search", "google.com"):
            if not query:
                webbrowser.open("https://www.google.com")
                return {"ok": True, "opened": "Google Home"}
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            webbrowser.open(search_url)
            return {"ok": True, "opened": f"Google search for: {query}"}

        else:
            # Maybe it's a direct URL or a domain (like github.com)
            if app_low.startswith("http") or "." in app_low:
                # If no http, assume https
                url = app_low if app_low.startswith("http") else f"https://{app_low}"
                webbrowser.open(url)
                return {"ok": True, "opened": url}
            
            # If nothing else, try a direct search on google
            search_url = f"https://www.google.com/search?q={app_low.replace(' ', '+')}"
            webbrowser.open(search_url)
            return {"ok": True, "opened": f"Searched for: {app_low} (Unsupported app fallback)"}

    except Exception as e:
        return {"ok": False, "error": str(e)}

    except Exception as e:
        return {"ok": False, "error": str(e)}

# ---------------------------------------------
# Camera: capture a photo
# ---------------------------------------------

@function_tool
async def capture_photo(filename: Optional[str] = None, camera_index: int = 0) -> Dict[str, Any]:
    """Capture a single photo from the default camera and save under Pictures/JarvisPhotos.

    Returns the saved path on success.
    """
    if not cv2:
        return {"ok": False, "error": "opencv (cv2) not installed"}
    try:
        save_dir = Path.home() / "Pictures" / "JarvisPhotos"
        save_dir.mkdir(parents=True, exist_ok=True)
        if not filename:
            filename = f"photo_{int(asyncio.get_event_loop().time() * 1000)}.jpg"
        save_path = save_dir / filename

        # capture on thread to avoid blocking
        def _capture():
            cam = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW if sys.platform.startswith("win") else 0)
            try:
                if not cam or not cam.isOpened():
                    return {"ok": False, "error": "Camera not available"}
                ret, frame = cam.read()
                if not ret:
                    return {"ok": False, "error": "Failed to read from camera"}
                # write JPEG
                cv2.imwrite(str(save_path), frame)
                return {"ok": True, "path": str(save_path)}
            finally:
                try:
                    cam.release()
                except Exception:
                    pass

        result = await asyncio.to_thread(_capture)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ---------------------------------------------
# WhatsApp Message Sender
# ---------------------------------------------

@function_tool
async def send_whatsapp_message(phone_number: str, message: str) -> Dict[str, Any]:
    """
    Send a WhatsApp message using WhatsApp Web.
    Requires WhatsApp Web login on browser.
    Example: phone_number='918765432100', message='Hello!'
    """
    try:
        if not phone_number or not message:
            return {"ok": False, "error": "Phone number and message required"}

        # encode spaces and some basic characters - for advanced usage use urllib.parse.quote_plus
        safe_text = message.replace(' ', '%20')
        whatsapp_url = f"https://api.whatsapp.com/send?phone={phone_number}&text={safe_text}"
        webbrowser.open(whatsapp_url)
        return {"ok": True, "sent_to": phone_number, "message": message}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# End of file

















