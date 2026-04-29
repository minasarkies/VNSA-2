"""
VNSA 2.0 - Voice Output v3
- ElevenLabs primary (streaming, full volume)
- Windows SAPI fallback with female voice (Zira/Eva) when ElevenLabs fails or quota exceeded
- Volume fixed: pygame initialised at max, gain applied to stream
"""
import io
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


def _safe_print(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


class VoiceOutput:
    def __init__(self, settings):
        self.settings   = settings
        self._q         = queue.Queue()
        self._stop_ev   = threading.Event()
        self._speaking  = False
        self._ready     = False
        self._error     = ""
        self._use_sapi  = False   # True when falling back to SAPI
        self._sapi_voice = self._detect_sapi_female()

        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        threading.Thread(target=self._test_connection, daemon=True).start()

    # ── Public API ────────────────────────────────────────────────────────────

    def speak(self, text: str, blocking: bool = False):
        if not text or not text.strip():
            return
        clean = self._clean(text)
        if not clean:
            return
        # Clear queue to avoid pile-up
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except Exception:
                break
        self._q.put(clean)
        if blocking:
            while self._speaking or not self._q.empty():
                time.sleep(0.05)

    def stop(self):
        self._stop_ev.set()
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except Exception:
                break
        self._speaking = False

    @property
    def is_ready(self) -> bool:
        return self._ready or self._use_sapi

    @property
    def error(self) -> str:
        return self._error

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    # ── SAPI female voice detection ───────────────────────────────────────────

    @staticmethod
    def _detect_sapi_female() -> str:
        """Return name of best available female SAPI voice."""
        if sys.platform != "win32":
            return ""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
                 "Add-Type -AssemblyName System.Speech; "
                 "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                 "$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"],
                capture_output=True, text=True, timeout=10,
                creationflags=0x08000000
            )
            voices = [v.strip() for v in result.stdout.splitlines() if v.strip()]
            # Prefer female voices in order
            preferred = ["Microsoft Zira", "Microsoft Eva", "Microsoft Hazel",
                         "Microsoft Susan", "Microsoft Helen"]
            for pref in preferred:
                for v in voices:
                    if pref.lower() in v.lower():
                        _safe_print(f"[Voice] SAPI fallback voice: {v}")
                        return v
            # Return any voice found
            if voices:
                return voices[0]
        except Exception as e:
            _safe_print(f"[Voice] SAPI voice detection error: {e}")
        return "Microsoft Zira Desktop"  # default attempt

    # ── Connection test ───────────────────────────────────────────────────────

    def _test_connection(self):
        key   = self.settings.elevenlabs_key
        voice = self.settings.elevenlabs_voice

        if not key or "YOUR" in key:
            self._error = "ElevenLabs API key not set"
            _safe_print(f"[Voice] WARN: {self._error} - using SAPI fallback")
            self._use_sapi = True
            return

        if not voice:
            self._error = "ElevenLabs Voice ID not set"
            _safe_print(f"[Voice] WARN: {self._error} - using SAPI fallback")
            self._use_sapi = True
            return

        try:
            import requests
            r = requests.get(
                "https://api.elevenlabs.io/v1/user",
                headers={"xi-api-key": key},
                timeout=8
            )
            if r.status_code == 200:
                # Check character quota
                info = r.json()
                used  = info.get("subscription", {}).get("character_count", 0)
                limit = info.get("subscription", {}).get("character_limit", 1)
                remaining = limit - used
                if remaining < 100:
                    self._error = f"ElevenLabs quota exhausted ({remaining} chars left)"
                    _safe_print(f"[Voice] WARN: {self._error} - using SAPI fallback")
                    self._use_sapi = True
                    return
                self._ready    = True
                self._use_sapi = False
                self._error    = ""
                _safe_print(f"[Voice] OK: ElevenLabs connected ({remaining} chars remaining)")
            elif r.status_code == 401:
                self._error    = "ElevenLabs API key invalid (401)"
                self._use_sapi = True
                _safe_print(f"[Voice] FAIL: {self._error} - using SAPI fallback")
            else:
                self._error    = f"ElevenLabs returned {r.status_code}"
                self._use_sapi = True
                _safe_print(f"[Voice] FAIL: {self._error} - using SAPI fallback")
        except Exception as e:
            self._error    = f"Cannot reach ElevenLabs: {e}"
            self._use_sapi = True
            _safe_print(f"[Voice] FAIL: {self._error} - using SAPI fallback")

    # ── Worker ────────────────────────────────────────────────────────────────

    def _worker(self):
        while True:
            try:
                text = self._q.get(timeout=1)
                if text is None:
                    break
                if self._stop_ev.is_set():
                    self._stop_ev.clear()
                    continue
                self._speaking = True
                if self._use_sapi:
                    self._sapi_speak(text)
                else:
                    self._el_speak(text)
                self._speaking = False
            except queue.Empty:
                continue
            except Exception as e:
                self._speaking = False
                _safe_print(f"[Voice] Worker error: {e}")

    # ── ElevenLabs ────────────────────────────────────────────────────────────

    def _el_speak(self, text: str):
        key   = self.settings.elevenlabs_key
        voice = self.settings.elevenlabs_voice
        try:
            import requests
            r = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream",
                headers={"xi-api-key": key, "Content-Type": "application/json",
                         "Accept": "audio/mpeg"},
                json={"text": text, "model_id": "eleven_turbo_v2",
                      "voice_settings": {"stability": 0.5, "similarity_boost": 0.75,
                                         "style": 0.0, "use_speaker_boost": True}},
                stream=True, timeout=20,
            )
            if r.status_code == 401:
                self._ready = False; self._use_sapi = True
                _safe_print("[Voice] ElevenLabs 401 - switched to SAPI")
                self._sapi_speak(text)
                return
            # 429 = quota exceeded
            if r.status_code == 429:
                self._use_sapi = True
                _safe_print("[Voice] ElevenLabs quota exceeded - switched to SAPI")
                self._sapi_speak(text)
                return
            if r.status_code != 200:
                _safe_print(f"[Voice] ElevenLabs {r.status_code} - using SAPI")
                self._sapi_speak(text)
                return
            audio = b"".join(r.iter_content(chunk_size=4096))
            self._play_mp3(audio)
        except Exception as e:
            _safe_print(f"[Voice] ElevenLabs error: {e} - using SAPI")
            self._sapi_speak(text)

    def _play_mp3(self, data: bytes):
        """Play MP3 at FULL volume."""
        # pygame — most reliable, always max volume
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.mixer.music.load(io.BytesIO(data))
            pygame.mixer.music.set_volume(1.0)   # MAX
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if self._stop_ev.is_set():
                    pygame.mixer.music.stop()
                    self._stop_ev.clear()
                    break
                time.sleep(0.02)
            return
        except Exception:
            pass

        # Temp file fallback
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(data)
            tmp = f.name
        try:
            flags = 0x08000000 if sys.platform == "win32" else 0
            # Try ffplay with full volume
            r = subprocess.run(
                ["ffplay", "-nodisp", "-autoexit", "-volume", "100",
                 "-loglevel", "quiet", tmp],
                timeout=60, creationflags=flags, capture_output=True
            )
            if r.returncode == 0:
                return
            # mpg123
            subprocess.run(["mpg123", "-q", tmp],
                           timeout=60, creationflags=flags, capture_output=True)
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    # ── SAPI fallback ─────────────────────────────────────────────────────────

    def _sapi_speak(self, text: str):
        """Speak using Windows SAPI with the detected female voice."""
        if sys.platform != "win32":
            _safe_print(f"[Voice] SAPI not available on {sys.platform}")
            return
        try:
            # Escape single quotes
            safe = text.replace("'", " ").replace('"', " ").replace("`", " ")
            # Truncate to avoid very long SAPI calls
            safe = safe[:600]
            voice_cmd = f"$s.SelectVoice('{self._sapi_voice}');" if self._sapi_voice else ""
            ps = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"{voice_cmd}"
                "$s.Rate = 1; "
                "$s.Volume = 100; "
                f"$s.Speak('{safe}');"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                timeout=60,
                creationflags=0x08000000
            )
        except Exception as e:
            _safe_print(f"[Voice] SAPI error: {e}")

    # ── Text cleaning ─────────────────────────────────────────────────────────

    @staticmethod
    def _clean(text: str) -> str:
        text = re.sub(r"```[\s\S]*?```", " ", text)
        text = re.sub(r"`[^`]+`", " ", text)
        text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
        text = re.sub(r"#+\s*", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        text = re.sub(r"[^\w\s.,!?;:()'\"%-]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()[:1200]
