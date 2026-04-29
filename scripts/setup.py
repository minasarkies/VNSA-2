"""
VNSA 2.0 — Setup Script
Run once: python scripts/setup.py
"""
import os
import sys
import subprocess
from pathlib import Path

ROOT    = Path(__file__).parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def run(cmd, cwd=None, check=True):
    print(f"  → {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd)
    if check and result.returncode != 0:
        print(f"  ✗ Failed (exit {result.returncode})")
        return False
    return True


def main():
    print("=" * 60)
    print("  VNSA 2.0 Setup")
    print("=" * 60)

    # ── 1. Python deps ────────────────────────────────────────────────────────
    print("\n[1/4] Installing Python dependencies...")
    run(f"{sys.executable} -m pip install -r requirements.txt",
        cwd=BACKEND)

    # ── 2. keys.env ───────────────────────────────────────────────────────────
    print("\n[2/4] Checking keys.env...")
    keys = BACKEND / "config" / "keys.env"
    example = BACKEND / "config" / "keys.env.example"
    if not keys.exists():
        import shutil
        shutil.copy(example, keys)
        print(f"  → Created {keys}")
        print("  ✎ Open backend/config/keys.env and fill in your API keys.")
    else:
        print("  ✓ keys.env exists")

    # ── 3. Node / Electron ────────────────────────────────────────────────────
    print("\n[3/4] Installing Electron...")
    if not run("npm install", cwd=FRONTEND):
        print("  ✗ npm not found. Install Node.js from https://nodejs.org")
        print("    Then run: cd frontend && npm install")
    else:
        print("  ✓ Electron installed")

    # ── 4. Windows Long Paths ─────────────────────────────────────────────────
    if sys.platform == "win32":
        print("\n[4/4] Enabling Windows long path support...")
        try:
            result = subprocess.run(
                ["reg", "query",
                 r"HKLM\SYSTEM\CurrentControlSet\Control\FileSystem",
                 "/v", "LongPathsEnabled"],
                capture_output=True, text=True
            )
            if "0x1" in result.stdout:
                print("  ✓ Long paths already enabled")
            else:
                run('reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem" '
                    '/v LongPathsEnabled /t REG_DWORD /d 1 /f',
                    check=False)
                print("  ✓ Long paths enabled")
        except Exception:
            print("  ⚠ Could not check — run as Administrator if needed")

    # ── Done ──────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Setup complete!")
    print()
    print("  Next steps:")
    print("  1. Edit backend/config/keys.env with your API keys")
    print("  2. Start backend:  cd backend && python main.py")
    print("  3. Start frontend: cd frontend && npm start")
    print("=" * 60)


if __name__ == "__main__":
    main()
