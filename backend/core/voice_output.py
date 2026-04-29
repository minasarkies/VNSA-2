"""
VNSA 2.0 — Voice Output v4
- ElevenLabs eleven_flash_v2_5 (fastest, most reliable model)
- Temp-file playback via pygame (avoids BytesIO/music.load unreliability)
- Correct stop-event lifecycle: set in stop(), cleared only in worker
- Retry logic for transient 429 / network errors
- Windows SAPI female-voice fallback when ElevenLabs is unavailable
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
        print(msg.encode("ascii", errors="replace").decode("ascii"))


class VoiceOutput:
    # ElevenLabs model — flash is faster and more reliable than turbo
    _EL_MODEL = "eleven_flash_v2_5"

    def __init__(self, settings):
        self.settings   = settings
        self._q         = queue.Queue()
        self._stop_ev   = threading.Event()
        self._speaking  = False
        self._ready     = False
        self._error     = ""
        self._use_sapi  = False
        self._sapi_voice = self._detect_sapi_female()
        self._proc      = None   # current subprocess handle (for forced kill)

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
        # Drain queue — only one pending utterance at a time
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
        """Immediately interrupt current speech and clear pending queue."""
        self._stop_ev.set()
        # Kill any active subprocess
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        # Try to stop pygame if active
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.stop()
        except Exception:
            pass
        # Drain queue
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except Exception:
                break

    @property
    def is_ready(self) -> bool:
        return self._ready or self._use_sapi

    @property
    def error(self) -> str:
        return self._error

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    # ── Connection test ───────────────────────────────────────────────────────

    def _test_connection(self):
        key   = self.settings.elevenlabs_key
        voice = self.settings.elevenlabs_voice

        if not key or "YOUR" in key.upper():
            self._error = "ElevenLabs API key not set in keys.env"
            _safe_print(f"[Voice] WARN: {self._error}")
            self._activate_sapi_fallback("ElevenLabs key not configured")
            return

        if not voice:
            self._error = "ElevenLabs Voice ID not set in keys.env"
            _safe_print(f"[Voice] WARN: {self._error}")
            self._activate_sapi_fallback("ElevenLabs voice ID not configured")
            return

        try:
            import requests
            r = requests.get(
                "https://api.elevenlabs.io/v1/user",
                headers={"xi-api-key": key},
                timeout=10,
            )
            if r.status_code == 200:
                self._ready     = True
                self._use_sapi  = False
                self._error     = ""
                _safe_print(f"[Voice] OK: ElevenLabs connected ({self._EL_MODEL})")
            elif r.status_code == 401:
                self._error = "ElevenLabs API key rejected (401). Check keys.env."
                _safe_print(f"[Voice] FAIL: {self._error}")
                self._activate_sapi_fallback(self._error)
            else:
                self._error = f"ElevenLabs returned HTTP {r.status_code}"
                _safe_print(f"[Voice] WARN: {self._error}")
                self._activate_sapi_fallback(self._error)
        except Exception as e:
            self._error = f"Cannot reach ElevenLabs: {e}"
            _safe_print(f"[Voice] WARN: {self._error}")
            self._activate_sapi_fallback(str(e))

    def _activate_sapi_fallback(self, reason: str):
        if self._sapi_voice:
            self._use_sapi = True
            _safe_print(f"[Voice] Falling back to SAPI ({self._sapi_voice}) — {reason}")
        else:
            _safe_print("[Voice] No SAPI voice available. Voice output disabled.")

    # ── Worker (runs in background thread) ───────────────────────────────────

    def _worker(self):
        while True:
            try:
                text = self._q.get(timeout=1)
                if text is None:
                    break

                # Check stop before starting anything
                if self._stop_ev.is_set():
                    self._stop_ev.clear()
                    continue

                self._speaking = True
                try:
                    if self._use_sapi:
                        self._sapi_speak(text)
                    else:
                        self._el_speak(text)
                finally:
                    self._speaking = False
                    # Clear stop event here (end of utterance), not in stop()
                    self._stop_ev.clear()

            except queue.Empty:
                continue
            except Exception as e:
                self._speaking = False
                self._stop_ev.clear()
                _safe_print(f"[Voice] Worker error: {e}")

    # ── ElevenLabs TTS ────────────────────────────────────────────────────────

    def _el_speak(self, text: str, _retry: int = 0):
        """Synthesise via ElevenLabs and play. Retries once on 429/timeout."""
        if not self._ready:
            if self._use_sapi:
                self._sapi_speak(text)
            return

        key   = self.settings.elevenlabs_key
        voice = self.settings.elevenlabs_voice

        try:
            import requests
            r = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                headers={
                    "xi-api-key":   key,
                    "Content-Type": "application/json",
                    "Accept":       "audio/mpeg",
                },
                json={
                    "text":     text,
                    "model_id": self._EL_MODEL,
                    "voice_settings": {
                        "stability":        0.45,
                        "similarity_boost": 0.80,
                        "style":            0.0,
                        "use_speaker_boost": True,
                    },
                },
                timeout=25,
            )

            if self._stop_ev.is_set():
                return

            if r.status_code == 401:
                self._ready = False
                self._error = "ElevenLabs key rejected (401). Update keys.env."
                _safe_print(f"[Voice] FAIL: {self._error}")
                self._activate_sapi_fallback(self._error)
                self._sapi_speak(text)
                return

            if r.status_code == 429:
                if _retry < 2:
                    wait = (2 ** _retry) * 1.5
                    _safe_print(f"[Voice] ElevenLabs 429 — retrying in {wait:.1f}s")
                    time.sleep(wait)
                    self._el_speak(text, _retry + 1)
                else:
                    _safe_print("[Voice] ElevenLabs 429 — falling back to SAPI")
                    self._sapi_speak(text)
                return

            if r.status_code != 200:
                _safe_print(f"[Voice] ElevenLabs error {r.status_code} — falling back to SAPI")
                self._sapi_speak(text)
                return

            audio = r.content
            if not audio:
                _safe_print("[Voice] Empty audio from ElevenLabs")
                return

            if not self._stop_ev.is_set():
                self._play_mp3_bytes(audio)

        except requests.exceptions.Timeout:
            if _retry < 1:
                _safe_print("[Voice] ElevenLabs timeout — retrying")
                self._el_speak(text, _retry + 1)
            else:
                _safe_print("[Voice] ElevenLabs timeout — falling back to SAPI")
                self._sapi_speak(text)
        except Exception as e:
            _safe_print(f"[Voice] ElevenLabs request failed: {e}")
            self._sapi_speak(text)

    # ── Audio playback ────────────────────────────────────────────────────────

    def _play_mp3_bytes(self, data: bytes):
        """Play raw MP3 bytes. Uses temp file for maximum pygame compatibility."""
        # Write to temp file — more reliable than BytesIO with pygame.mixer.music
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(data)
                tmp_path = f.name

            self._play_file(tmp_path)
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    def _play_file(self, path: str):
        """Play an audio file. Tries pygame first, then subprocess fallbacks."""

        # ── pygame (preferred) ────────────────────────────────────────────────
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(1.0)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if self._stop_ev.is_set():
                    pygame.mixer.music.stop()
                    return
                time.sleep(0.02)
            return
        except Exception as e:
            _safe_print(f"[Voice] pygame failed: {e} — trying subprocess")

        # ── ffplay fallback ───────────────────────────────────────────────────
        flags = 0x08000000 if sys.platform == "win32" else 0
        try:
            self._proc = subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", "-volume", "100",
                 "-loglevel", "quiet", path],
                creationflags=flags,
            )
            while self._proc.poll() is None:
                if self._stop_ev.is_set():
                    self._proc.terminate()
                    return
                time.sleep(0.05)
            self._proc = None
            return
        except FileNotFoundError:
            pass
        except Exception as e:
            _safe_print(f"[Voice] ffplay failed: {e}")

        # ── mpg123 fallback ───────────────────────────────────────────────────
        try:
            self._proc = subprocess.Popen(
                ["mpg123", "-q", path],
                creationflags=flags,
            )
            while self._proc.poll() is None:
                if self._stop_ev.is_set():
                    self._proc.terminate()
                    return
                time.sleep(0.05)
            self._proc = None
            return
        except FileNotFoundError:
            pass
        except Exception as e:
            _safe_print(f"[Voice] mpg123 failed: {e}")

        _safe_print("[Voice] No audio player available. Install pygame: pip install pygame")

    # ── SAPI fallback ─────────────────────────────────────────────────────────

    @staticmethod
    def _detect_sapi_female() -> str:
        """Return the name of the best available female SAPI voice, or ''."""
        if sys.platform != "win32":
            return ""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Add-Type -AssemblyName System.Speech; "
                 "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                 "$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"],
                capture_output=True, text=True, timeout=8,
                creationflags=0x08000000,
            )
            voices = result.stdout.strip().splitlines()
            preferred = ["Zira", "Eva", "Hazel"]
            for pref in preferred:
                for v in voices:
                    if pref.lower() in v.lower():
                        return v
            # Return any female-sounding voice
            for v in voices:
                if any(n in v for n in ["Zira", "Eva", "Hazel", "Helen", "Susan"]):
                    return v
            return voices[0] if voices else ""
        except Exception:
            return ""

    def _sapi_speak(self, text: str):
        if not self._sapi_voice or sys.platform != "win32":
            return
        try:
            escaped = text.replace('"', "'").replace("'", "\\'")
            script = (
                "Add-Type -AssemblyName System.Speech; "
                f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.SelectVoice('{self._sapi_voice}'); "
                f"$s.Rate = 0; "
                f"$s.Volume = 100; "
                f"$s.Speak(\"{escaped}\");"
            )
            self._proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                 "-Command", script],
                creationflags=0x08000000,
            )
            while self._proc.poll() is None:
                if self._stop_ev.is_set():
                    self._proc.terminate()
                    return
                time.sleep(0.05)
            self._proc = None
        except Exception as e:
            _safe_print(f"[Voice] SAPI error: {e}")

    # ── Text cleaning ─────────────────────────────────────────────────────────

    @staticmethod
    def _clean(text: str) -> str:
        # Remove code blocks
        text = re.sub(r"```[\s\S]*?```", " code block ", text)
        text = re.sub(r"`[^`\n]+`", " ", text)
        # Remove markdown formatting
        text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
        text = re.sub(r"#+\s*", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        # Remove URLs
        text = re.sub(r"https?://\S+", " link ", text)
        # Remove non-speakable characters
        text = re.sub(r"[^\w\s.,!?;:()'\"%-]", " ", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        # Cap at 1500 chars to prevent extremely long TTS
        return text.strip()[:1500]
