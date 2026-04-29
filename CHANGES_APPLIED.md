# VNSA 2.0 — Patch 3: Full Audit & Fixes

## Issues Found & Fixed

---

### 🔴 CRITICAL: Hardcoded credentials in repo (setup_auth.py)
**File:** `backend/config/setup_auth.py`
**Problem:** Real email address and password were hardcoded in plaintext. Anyone who ever accessed the repo could see them.
**Fix:** File completely rewritten as an interactive CLI setup tool — it uses `getpass` (password never shown), no credentials stored in code.
**Action required:** Re-run `python backend/config/setup_auth.py` to reset credentials.

---

### 🔴 Email never worked (VNSA's implementation)
**Files:** `backend/tools/email.py` + `frontend/src/index.html` JS
**Problem:** Two completely separate systems:
- VNSA's settings panel wrote `EMAIL_ACCOUNTS` + `EMAIL_DEFAULT` to `keys.env`
- The email tool read from `backend/config/email_credentials.json`
- These never communicated — email was broken from day one

Also: the settings panel had only two fields (accounts string + default), but the tool needs `imap_host`, `imap_port`, `smtp_host`, `smtp_port`, `email`, `password` per account.

**Fix:**
- `email.py` cleaned up with better error messages, proper validation, retry-safe SMTP
- `index.html` email settings panel completely redesigned:
  - Writes directly to `email_credentials.json` (the file the tool actually reads)
  - Has all required fields (email, password, IMAP host/port, SMTP host/port)
  - Auto-fills IMAP/SMTP servers when you type a Gmail/Outlook/Yahoo/iCloud address
  - Upsert logic — saves multiple accounts without overwriting others
- Added `backend/config/email_credentials.example.json` as a reference
- Added `PROVIDER_PRESETS` in `email.py` for documentation

**Setup:** In Settings → Email Setup, enter your email + Gmail App Password, click Save. Gmail/Outlook/Yahoo/iCloud auto-fill their server settings.

---

### 🟡 Voice unreliable (ElevenLabs)
**File:** `backend/core/voice_output.py`
**Problems found:**
1. `pygame.mixer.music.load(io.BytesIO(data))` — pygame's music module is unreliable with in-memory MP3 on Windows; occasionally fails silently
2. Model was `eleven_turbo_v2` — not the fastest/most reliable option
3. Stop event cleared in `_play_audio()` (inside the worker's call stack) — but `stop()` could be called externally, leaving the event set and causing the *next* utterance to be immediately discarded
4. No retry on transient 429 rate-limit errors

**Fixes:**
- Model upgraded to `eleven_flash_v2_5` (fastest model, better reliability)
- Switched to **temp file** approach: audio written to `.mp3` temp file, pygame loads from disk path (100% reliable on Windows)
- Stop event lifecycle fixed: `stop()` sets it, worker clears it at the *end* of each utterance — new messages are never accidentally skipped
- Added exponential backoff retry (up to 2 retries) on 429 and timeout errors
- Subprocess handle (`_proc`) stored so `stop()` can `terminate()` active ffplay/mpg123
- SAPI fallback still works as safety net

---

### 🟡 Fullscreen still translucent
**Files:** `frontend/src/main.js` + `frontend/src/index.html` CSS
**Problem:** 
- `main.js` `toggleFullscreen()` never changed the window's `backgroundColor` — the Electron window stayed fully transparent, showing desktop through it
- CSS `#shell.fs` only removed `border-radius`; `backdrop-filter:blur(24px)` and `rgba` background remained active

**Fix:**
- `main.js`: `toggleFullscreen()` now calls `mainWindow.setBackgroundColor('#020912')` when entering fullscreen, and `'#00000000'` when returning to widget mode
- CSS `#shell.fs` now sets `background: var(--c-bg) !important` (solid `#020912`) and `backdrop-filter: none !important`

---

### 🟡 Token limits cut off complex responses
**File:** `backend/core/agent.py`
**Problems:**
- `max_tokens: 1024` — responses to complex questions got cut mid-sentence
- Tool output capped at `1500` chars — web search results, file reads, etc. were truncated too aggressively
- Tool loop max 5 iterations — not enough for multi-step tasks
- Rate-limit fallback jumped straight to Haiku+512 tokens (major intelligence drop)
- Memory search only top 3 results at 100 chars each

**Fixes:**
- `max_tokens` raised to `4096` for all chat and tool-loop calls
- Tool output cap raised from `1500` → `8000` chars
- Tool loop max iterations: `5` → `10`
- Rate-limit fallback chain: same model + trim to 4 messages → same model + trim to 2 → Haiku+2048 (last resort only)
- Conversation history extended to 20 messages (10 turns)
- Memory: top 5 results at 150 chars each

---

## How to apply

### Files to REPLACE entirely:
```
backend/config/setup_auth.py          ← from fixes/backend/config/
backend/core/voice_output.py          ← from fixes/backend/core/
backend/core/agent.py                 ← from fixes/backend/core/
backend/tools/email.py                ← from fixes/backend/tools/
```

### Files to ADD:
```
backend/config/email_credentials.example.json   ← from fixes/backend/config/
```

### Manual patches required (see fixes/frontend/src/index.html.patches.js):

**main.js** — Replace the `toggleFullscreen()` function (see `fixes/frontend/src/main.js.patch.js`)

**index.html** — Three changes:
1. **CSS**: Replace `#shell` + `#shell.fs` rules (Patch A in patches file)
2. **JS**: Replace the `// ── Email settings ──` section (Patch B in patches file)
3. **HTML**: Replace the email srow block in the settings panel (Patch C in patches file)

---

## Security notes
- `backend/config/.vnsa_auth.json` — hashed credentials, never commit
- `backend/config/email_credentials.json` — App Passwords, never commit
- `backend/config/.session_secret` — session key, never commit
- All three are already in `.gitignore` (verify this!)

Add to `.gitignore` if missing:
```
backend/config/.vnsa_auth.json
backend/config/email_credentials.json
backend/config/.session_secret
backend/config/.pin_hash
.backups/
```
