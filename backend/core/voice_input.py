"""VNSA 2.0 - Voice Input. Whisper STT with Google fallback."""
import queue
import threading
import time


def _safe_print(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


class VoiceInput:
    def __init__(self, settings):
        self.settings = settings
        self._ready   = False
        self._error   = ""
        threading.Thread(target=self._test_mic, daemon=True).start()

    def _test_mic(self):
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            m = sr.Microphone()
            with m as source:
                r.adjust_for_ambient_noise(source, duration=0.5)
            self._ready = True
            self._error = ""
            _safe_print("[VoiceIn] OK: Microphone ready")
        except Exception as e:
            self._ready = False
            self._error = f"Microphone not accessible: {e}"
            _safe_print(f"[VoiceIn] FAIL: {self._error}")

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def error(self) -> str:
        return self._error

    def listen_once(self) -> str:
        if not self._ready:
            return ""
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            r.dynamic_energy_threshold = True
            r.pause_threshold = 0.8
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source, duration=0.4)
                audio = r.listen(source, timeout=10, phrase_time_limit=30)
            return self._transcribe(r, audio)
        except Exception as e:
            _safe_print(f"[VoiceIn] Listen error: {e}")
            return ""

    def stop(self):
        pass  # interrupt handled by caller cancelling the task

    def _transcribe(self, r, audio) -> str:
        import speech_recognition as sr
        try:
            return r.recognize_whisper(audio, model=self.settings.whisper_model).strip()
        except sr.UnknownValueError:
            return ""
        except Exception:
            pass
        try:
            return r.recognize_google(audio).strip()
        except Exception:
            return ""
