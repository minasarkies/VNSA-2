"""VNSA 2.0 — Desktop control."""
import os
import subprocess
import sys

TOOL_DEFINITION = {
    "name": "desktop",
    "description": "Control the desktop: open apps, run system commands, send keyboard shortcuts.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string",
                       "enum": ["open_app", "run_command", "shortcut",
                                "type_text", "clipboard_read", "clipboard_write",
                                "volume_up", "volume_down", "mute",
                                "lock_screen", "sleep"]},
            "target": {"type": "string", "description": "App name or command"},
            "keys":   {"type": "string", "description": "Keyboard shortcut e.g. ctrl+c"},
            "text":   {"type": "string", "description": "Text to type or clipboard content"},
        },
        "required": ["action"],
    },
}


def run(action: str, target: str = "", keys: str = "",
        text: str = "", **_) -> str:
    try:
        if action == "open_app":
            return _open_app(target)
        if action == "run_command":
            return _run_cmd(target)
        if action == "shortcut":
            return _shortcut(keys)
        if action == "type_text":
            import pyautogui
            pyautogui.typewrite(text, interval=0.02)
            return f"Typed: {text[:50]}"
        if action == "clipboard_read":
            return _clip_read()
        if action == "clipboard_write":
            return _clip_write(text)
        if action == "volume_up":
            return _media_key("volume_up", 5)
        if action == "volume_down":
            return _media_key("volume_down", 5)
        if action == "mute":
            return _media_key("volume_mute")
        if action == "lock_screen":
            if sys.platform == "win32":
                subprocess.run(["rundll32", "user32.dll,LockWorkStation"])
            return "Screen locked."
        if action == "sleep":
            if sys.platform == "win32":
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            return "Going to sleep."
        return f"Unknown action: {action}"
    except ImportError as e:
        return f"Missing dependency: {e}. Run: pip install pyautogui pyperclip"
    except Exception as e:
        return f"Desktop error: {e}"


def _open_app(name: str) -> str:
    aliases = {
        "chrome":     "chrome",
        "firefox":    "firefox",
        "notepad":    "notepad",
        "explorer":   "explorer",
        "calculator": "calc",
        "terminal":   "wt",
        "powershell": "powershell",
        "task manager": "taskmgr",
        "paint":      "mspaint",
        "word":       "winword",
        "excel":      "excel",
        "outlook":    "outlook",
        "teams":      "teams",
        "vs code":    "code",
        "vscode":     "code",
    }
    cmd = aliases.get(name.lower(), name)
    try:
        subprocess.Popen(cmd, shell=True)
        return f"Opened: {name}"
    except Exception as e:
        return f"Could not open {name}: {e}"


def _run_cmd(cmd: str) -> str:
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True,
                                text=True, timeout=15)
        out = (result.stdout or result.stderr or "").strip()
        return out[:1000] if out else "Command executed."
    except subprocess.TimeoutExpired:
        return "Command timed out."
    except Exception as e:
        return f"Command error: {e}"


def _shortcut(keys: str) -> str:
    if not keys:
        return "Provide keys parameter."
    import pyautogui
    parts = [k.strip() for k in keys.lower().split("+")]
    pyautogui.hotkey(*parts)
    return f"Shortcut sent: {keys}"


def _clip_read() -> str:
    try:
        import pyperclip
        content = pyperclip.paste()
        return f"Clipboard: {content[:500]}" if content else "(Clipboard empty)"
    except Exception:
        if sys.platform == "win32":
            r = subprocess.run(["powershell", "-command", "Get-Clipboard"],
                               capture_output=True, text=True, timeout=5)
            return r.stdout.strip() or "(empty)"
        return "pyperclip not installed."


def _clip_write(text: str) -> str:
    try:
        import pyperclip
        pyperclip.copy(text)
        return f"Copied to clipboard ({len(text)} chars)."
    except Exception:
        return "Could not write to clipboard."


def _media_key(key: str, times: int = 1) -> str:
    import pyautogui
    for _ in range(times):
        pyautogui.press(key)
    return f"Key pressed: {key}"
