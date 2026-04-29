"""VNSA 2.0 Settings — single source of truth for all config."""
import json
import os
from pathlib import Path
from dotenv import load_dotenv

CONFIG_DIR   = Path(__file__).parent
KEYS_FILE    = CONFIG_DIR / "keys.env"
PREFS_FILE   = CONFIG_DIR / "prefs.json"
PERSONA_FILE = CONFIG_DIR / "persona.txt"


class Settings:
    def __init__(self):
        self._load_env()
        self._load_prefs()

    def _load_env(self):
        if KEYS_FILE.exists():
            load_dotenv(KEYS_FILE, encoding="utf-8-sig")
        # API keys
        self.anthropic_key    = os.getenv("ANTHROPIC_API_KEY", "")
        self.elevenlabs_key   = os.getenv("ELEVENLABS_API_KEY", "")
        self.elevenlabs_voice = os.getenv("ELEVENLABS_VOICE_ID", "")
        self.perplexity_key   = os.getenv("PERPLEXITY_API_KEY", "")
        self.spotify_id       = os.getenv("SPOTIFY_CLIENT_ID", "")
        self.spotify_secret   = os.getenv("SPOTIFY_CLIENT_SECRET", "")
        self.github_token     = os.getenv("GITHUB_TOKEN", "")
        self.gist_id          = os.getenv("GITHUB_GIST_ID", "").split("#")[0].strip()
        # Identity
        self.user_name        = os.getenv("USER_NAME", "Sir")
        # Models
        self.claude_model     = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        self.whisper_model    = os.getenv("WHISPER_MODEL", "base")
        # Memory
        self.memory_backend   = os.getenv("MEMORY_BACKEND", "local")

    def _load_prefs(self):
        defaults = {
            "mode": "ECHO",
            "startup_greeting": True,
            "lens_interval": 8,
            "theme_accent": "#38bdf8",
            "lens_enabled": False,
        }
        if PREFS_FILE.exists():
            try:
                saved = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
                defaults.update(saved)
            except Exception:
                pass
        for k, v in defaults.items():
            setattr(self, k, v)

    def update(self, d: dict):
        for k, v in d.items():
            setattr(self, k, v)
        prefs = {k: getattr(self, k) for k in
                 ["mode", "startup_greeting", "lens_interval",
                  "theme_accent", "lens_enabled"]}
        PREFS_FILE.write_text(json.dumps(prefs, indent=2), encoding="utf-8")

    @property
    def persona(self) -> str:
        if PERSONA_FILE.exists():
            return PERSONA_FILE.read_text(encoding="utf-8").replace(
                "{user_name}", self.user_name)
        return f"You are VNSA, {self.user_name}'s AI assistant."

    def validate(self) -> dict:
        """Return dict of key → ok/missing for health monitor."""
        return {
            "anthropic":    bool(self.anthropic_key and "YOUR" not in self.anthropic_key),
            "elevenlabs":   bool(self.elevenlabs_key and "YOUR" not in self.elevenlabs_key),
            "voice_id":     bool(self.elevenlabs_voice),
            "perplexity":   bool(self.perplexity_key and "YOUR" not in self.perplexity_key),
        }
