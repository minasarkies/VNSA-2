"""
VNSA 2.0 — Self-Modify Tool
Allows VNSA to read, write, and patch her own source files.
"""
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

# Project root = two levels up from this file (tools/ -> backend/ -> project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent

TOOL_DEFINITION = {
    "name": "self_modify",
    "description": (
        "Read or write VNSA's own source files. "
        "Use to implement new features, fix bugs, or update configuration. "
        "Always read a file before writing it. "
        "Backend Python changes require a backend restart to take effect. "
        "Frontend HTML/JS changes take effect on next Electron reload."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "patch", "list", "backup"],
                "description": "read=get file contents, write=replace entire file, patch=find+replace section, list=show project files, backup=copy file before editing"
            },
            "path": {
                "type": "string",
                "description": "Relative path from project root, e.g. 'backend/tools/email.py' or 'frontend/src/index.html'"
            },
            "content": {
                "type": "string",
                "description": "New file content for write action"
            },
            "old_text": {
                "type": "string",
                "description": "Exact text to find and replace (for patch action)"
            },
            "new_text": {
                "type": "string",
                "description": "Replacement text (for patch action)"
            },
        },
        "required": ["action"],
    },
}


def run(action: str, path: str = "", content: str = "",
        old_text: str = "", new_text: str = "") -> str:

    if action == "list":
        return _list_files()

    if not path:
        return "Provide a path."

    # Sanitise path — prevent escaping project root
    clean = path.replace("\\", "/").lstrip("/")
    target = (PROJECT_ROOT / clean).resolve()
    if not str(target).startswith(str(PROJECT_ROOT.resolve())):
        return "Access denied — path outside project root."

    if action == "read":
        return _read(target)

    if action == "backup":
        return _backup(target)

    if action == "write":
        if not content:
            return "Provide content to write."
        return _write(target, content)

    if action == "patch":
        if not old_text:
            return "Provide old_text to find."
        return _patch(target, old_text, new_text)

    return f"Unknown action: {action}"


def _read(path: Path) -> str:
    if not path.exists():
        return f"File not found: {path.relative_to(PROJECT_ROOT)}"
    try:
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        rel = path.relative_to(PROJECT_ROOT)
        header = f"# {rel}  ({len(lines)} lines)\n"
        # Return with line numbers for easier patching
        numbered = "\n".join(f"{i+1:4}: {l}" for i, l in enumerate(lines))
        return header + numbered
    except Exception as e:
        return f"Read error: {e}"


def _write(path: Path, content: str) -> str:
    try:
        # Auto-backup before overwriting
        _backup(path, silent=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        rel = path.relative_to(PROJECT_ROOT)
        lines = content.count("\n") + 1
        return (f"✅ Written: {rel} ({lines} lines). "
                f"{'Restart backend to apply.' if path.suffix == '.py' and 'backend' in str(path) else 'Changes applied.'}")
    except Exception as e:
        return f"Write error: {e}"


def _patch(path: Path, old_text: str, new_text: str) -> str:
    if not path.exists():
        return f"File not found: {path.relative_to(PROJECT_ROOT)}"
    try:
        _backup(path, silent=True)
        original = path.read_text(encoding="utf-8")
        if old_text not in original:
            return (f"Text not found in {path.name}. "
                    f"Use action='read' to see the exact current content before patching.")
        updated = original.replace(old_text, new_text, 1)
        path.write_text(updated, encoding="utf-8")
        rel = path.relative_to(PROJECT_ROOT)
        return (f"✅ Patched: {rel}. "
                f"{'Restart backend to apply.' if path.suffix == '.py' and 'backend' in str(path) else 'Changes applied.'}")
    except Exception as e:
        return f"Patch error: {e}"


def _backup(path: Path, silent: bool = False) -> str:
    if not path.exists():
        return "Nothing to backup — file doesn't exist yet."
    try:
        backup_dir = PROJECT_ROOT / ".backups"
        backup_dir.mkdir(exist_ok=True)
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        rel = path.relative_to(PROJECT_ROOT)
        backup_name = str(rel).replace("/", "_").replace("\\", "_")
        dest = backup_dir / f"{backup_name}.{ts}.bak"
        shutil.copy2(path, dest)
        if not silent:
            return f"✅ Backup saved: .backups/{dest.name}"
        return ""
    except Exception as e:
        return f"Backup error: {e}"


def _list_files() -> str:
    """List key project files VNSA can modify."""
    lines = ["VNSA 2.0 — Modifiable files:", ""]
    important = [
        "backend/core/agent.py",
        "backend/core/voice_output.py",
        "backend/core/voice_input.py",
        "backend/core/health_monitor.py",
        "backend/main.py",
        "backend/config/persona.txt",
        "backend/config/keys.env",
        "backend/memory/manager.py",
        "frontend/src/index.html",
        "frontend/src/lens.html",
        "frontend/src/main.js",
    ]
    for p in important:
        full = PROJECT_ROOT / p
        if full.exists():
            size = full.stat().st_size
            lines.append(f"  {'✓' if full.exists() else '✗'} {p}  ({size:,} bytes)")

    lines.append("\nTools:")
    tools_dir = PROJECT_ROOT / "backend" / "tools"
    if tools_dir.exists():
        for f in sorted(tools_dir.glob("*.py")):
            if not f.name.startswith("_"):
                lines.append(f"  ✓ backend/tools/{f.name}")

    return "\n".join(lines)
