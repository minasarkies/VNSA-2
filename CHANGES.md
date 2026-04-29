# VNSA 2.0 — Patch 2

## Files to replace / add

| File | Action | What changed |
|------|--------|--------------|
| `backend/main.py` | **REPLACE** | Voice interrupt, mode-gated TTS, file attachments |
| `backend/core/agent.py` | **REPLACE** | `chat_with_content()` for file attachments |
| `backend/config/persona.txt` | **REPLACE** | VNSA knows she can self-modify |
| `backend/tools/self_modify.py` | **ADD** | VNSA reads/writes her own source |
| `backend/tools/generate_document.py` | **ADD** | Generates MD/TXT/HTML/DOCX/PDF |
| `frontend/src/main.js` | **REPLACE** | PIN flow, fullscreen, tray |
| `frontend/src/index.html` | **REPLACE** | File attachments, fullscreen btn, mode fix |
| `frontend/src/pin.html` | **ADD** | PIN lock screen |
| `launcher/VNSA.bat` | **ADD** | Single double-click launcher |

## How to apply

1. Copy all files to your repo maintaining the same folder structure
2. No pip installs needed for most changes
3. Optional extras:
   ```
   pip install python-docx weasyprint fpdf2
   ```
   (for full document generation support)

---

## What each change does

### 1. Voice interrupt
When you send a new message while VNSA is speaking, `voice_out.stop()` is
called immediately before processing the new input. She cuts off mid-sentence
and responds to the new context.

### 2. Mode-gated TTS
- **CIPHER** — no TTS ever. Text only.
- **ECHO** — VNSA speaks every response. You type.
- **NEXUS** — continuous mic + VNSA speaks. Full bidirectional.
The backend now checks `settings.mode` before calling `voice_out.speak()`.

### 3. Self-modification (`backend/tools/self_modify.py`)
VNSA can now:
- `list` — show all her source files
- `read` — read any file in the project (with line numbers)
- `write` — replace an entire file
- `patch` — find and replace a specific section
- `backup` — save a timestamped copy before editing (auto-called on write/patch)
All writes are auto-backed-up to `.backups/` before changing anything.
She cannot access files outside the project root (security boundary).

### 4. File attachments
- 📎 button opens file picker (or drag & drop onto chat)
- Multiple files at once
- Images sent as base64 to Claude Vision
- Text/code/PDF files decoded and included as text context
- File badges shown in chat message
- Supported: images, PDF, TXT, MD, PY, JS, HTML, CSS, JSON, CSV, DOCX, XLSX

### 5. Document generation (`backend/tools/generate_document.py`)
Ask VNSA to "write a report" / "create a document" / "save this as a PDF".
Outputs saved to `~/Documents/VNSA/`.
Formats: `.md`, `.txt`, `.html`, `.docx` (needs python-docx), `.pdf` (needs weasyprint or fpdf2)

### 6. PIN lock screen (`frontend/src/pin.html`)
- Shown before main UI on every launch
- First launch: set a 4–6 digit PIN
- Subsequent launches: enter PIN to unlock
- PIN stored as SHA-256 hash (never plain text)
- 5 wrong attempts → app closes
- Animated, matches VNSA aesthetic

### 7. Fullscreen
- Click the ⛶ button in title bar, or press F11, or double-click the orb
- Toggles between full screen and side-panel mode
- Tray menu also has Fullscreen option

### 8. Single launcher (`launcher/VNSA.bat`)
- Drop `VNSA.bat` anywhere (desktop, taskbar, etc.)
- Double-click → checks Python + Node → installs if needed → launches
- No terminal windows stay open
- On first run: opens keys.env in Notepad if not configured

### 9. LENS fix
- Screenshot capture now properly calls `send('lens_frame', ...)` every 8s
- Insights broadcast from backend land on `lens_insight` event
- Frontend forwards to lens window via `ipcRenderer.send('lens-insight', ...)`
- Lens window renders the card correctly
