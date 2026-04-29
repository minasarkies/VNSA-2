"""
VNSA 2.0 — Health Monitor
VNSA's self-awareness system. Continuously checks all subsystems
and surfaces issues to the user in plain language with suggested fixes.
"""
import asyncio
import time
from datetime import datetime
from typing import Optional


FIXES = {
    "elevenlabs_key": (
        "My voice API key isn't configured. Open `backend/config/keys.env` "
        "and add your ElevenLabs API key as `ELEVENLABS_API_KEY=...`."
    ),
    "elevenlabs_voice": (
        "My voice ID isn't set. Open `backend/config/keys.env` and add "
        "`ELEVENLABS_VOICE_ID=...` with your ElevenLabs voice ID."
    ),
    "elevenlabs_auth": (
        "My ElevenLabs API key is being rejected. Please generate a new key "
        "at elevenlabs.io and update `ELEVENLABS_API_KEY` in keys.env."
    ),
    "elevenlabs_network": (
        "I can't reach ElevenLabs — looks like a network issue. "
        "Check your internet connection, then I'll retry automatically."
    ),
    "microphone": (
        "I can't access your microphone. Check that no other app has it locked, "
        "and that Python has microphone permission in Windows Settings → Privacy → Microphone."
    ),
    "anthropic_key": (
        "My Anthropic API key isn't configured. Open keys.env and add "
        "`ANTHROPIC_API_KEY=sk-ant-...`."
    ),
    "anthropic_auth": (
        "My Anthropic API key is being rejected. Please check or regenerate "
        "your key at console.anthropic.com."
    ),
    "pygame": (
        "Audio playback (pygame) isn't installed. Run: `pip install pygame`"
    ),
}


class HealthCheck:
    def __init__(self, name: str, ok: bool, detail: str = "", fix: str = ""):
        self.name   = name
        self.ok     = ok
        self.detail = detail
        self.fix    = fix

    def to_dict(self) -> dict:
        return {"ok": self.ok, "detail": self.detail, "fix": self.fix}


class HealthMonitor:
    def __init__(self, settings, voice_out, voice_in, agent):
        self.settings  = settings
        self.voice_out = voice_out
        self.voice_in  = voice_in
        self.agent     = agent
        self._last_run: Optional[float] = None
        self._cache: Optional[dict]     = None

    async def get_status(self) -> dict:
        """Run all health checks and return status dict."""
        now = time.time()
        # Cache for 15 seconds to avoid hammering APIs
        if self._cache and self._last_run and (now - self._last_run) < 15:
            return self._cache

        checks = {}
        checks["voice_output"] = await self._check_voice_output()
        checks["voice_input"]  = await self._check_voice_input()
        checks["anthropic"]    = await self._check_anthropic()
        checks["audio_player"] = await self._check_audio_player()

        overall_ok = all(c.ok for c in checks.values())
        issues = [name for name, c in checks.items() if not c.ok]

        result = {
            "ok":        overall_ok,
            "issues":    issues,
            "checks":    {k: v.to_dict() for k, v in checks.items()},
            "timestamp": datetime.now().isoformat(),
        }
        self._cache    = result
        self._last_run = now
        return result

    # ── Individual checks ─────────────────────────────────────────────────────

    async def _check_voice_output(self) -> HealthCheck:
        # Use the VoiceOutput's own status (it tested on init)
        if not self.voice_out.is_ready:
            err = self.voice_out.error
            # Determine specific fix
            if "key" in err.lower() and "not configured" in err.lower():
                fix_key = "elevenlabs_key"
            elif "voice id" in err.lower():
                fix_key = "elevenlabs_voice"
            elif "401" in err or "rejected" in err.lower():
                fix_key = "elevenlabs_auth"
            else:
                fix_key = "elevenlabs_network"
            return HealthCheck("voice_output", False, err, FIXES[fix_key])
        return HealthCheck("voice_output", True, "ElevenLabs connected")

    async def _check_voice_input(self) -> HealthCheck:
        if not self.voice_in.is_ready:
            return HealthCheck(
                "voice_input", False,
                self.voice_in.error,
                FIXES["microphone"]
            )
        return HealthCheck("voice_input", True, "Microphone ready")

    async def _check_anthropic(self) -> HealthCheck:
        key = self.settings.anthropic_key
        if not key or "YOUR" in key:
            return HealthCheck("anthropic", False,
                               "API key not configured", FIXES["anthropic_key"])
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            # Cheapest possible test call
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=5,
                messages=[{"role": "user", "content": "hi"}]
            )
            return HealthCheck("anthropic", True, "Connected")
        except anthropic.AuthenticationError:
            return HealthCheck("anthropic", False,
                               "API key rejected", FIXES["anthropic_auth"])
        except Exception as e:
            return HealthCheck("anthropic", False, str(e), FIXES["anthropic_key"])

    async def _check_audio_player(self) -> HealthCheck:
        try:
            import pygame
            return HealthCheck("audio_player", True, "pygame available")
        except ImportError:
            return HealthCheck("audio_player", False,
                               "pygame not installed", FIXES["pygame"])

    # ── Issue description ─────────────────────────────────────────────────────

    def describe_issues(self, issue_keys: list) -> str:
        """Generate a natural language health report for VNSA to speak/display."""
        if not issue_keys:
            return ""

        lines = ["Sir, I've detected some issues with my systems:"]
        for key in issue_keys:
            status = self._cache["checks"].get(key, {})
            detail = status.get("detail", "")
            fix    = status.get("fix", "")
            lines.append(f"\n**{key.replace('_', ' ').title()}**: {detail}")
            if fix:
                lines.append(f"→ {fix}")

        lines.append("\nLet me know if you'd like help fixing any of these.")
        return "\n".join(lines)
