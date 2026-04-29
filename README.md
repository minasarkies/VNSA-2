# VNSA 2.0 — Virtual Neural Synthetic Assistant

A complete rebuild. Electron frontend + Python FastAPI backend.
Animated, self-aware, seamless.

## Quick Start

### 1. Install Python backend
```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure keys
```bash
cp backend/config/keys.env.example backend/config/keys.env
# Edit keys.env and fill in your API keys
```

### 3. Install frontend
```bash
cd frontend
npm install
```

### 4. Run (both together)
```bash
# Terminal 1 — backend
cd backend && python main.py

# Terminal 2 — frontend
cd frontend && npm start
```

## Structure
```
VNSA-2/
├── backend/          Python FastAPI — AI brain, voice, tools, memory
│   ├── core/         Agent, voice I/O, health monitor
│   ├── tools/        Email, calendar, web search, peripherals, desktop
│   ├── memory/       Persistent memory with sync
│   └── config/       Keys, settings, persona
├── frontend/         Electron — animated UI
│   └── src/          HTML/CSS/JS — all UI code
└── scripts/          Setup, migration, diagnostics
```
