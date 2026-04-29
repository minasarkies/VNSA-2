"""VNSA 2.0 — Memory Manager."""
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

MEMORY_FILE = Path(__file__).parent.parent / "config" / "memory.json"


class MemoryManager:
    def __init__(self, settings):
        self.settings = settings
        self._entries: list[dict] = []
        self._load()

    def _load(self):
        if MEMORY_FILE.exists():
            try:
                data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
                self._entries = data.get("entries", [])
            except Exception:
                self._entries = []

    def _save(self):
        MEMORY_FILE.parent.mkdir(exist_ok=True)
        MEMORY_FILE.write_text(
            json.dumps({"version": "2.0",
                        "owner": self.settings.user_name,
                        "entries": self._entries,
                        "updated": datetime.utcnow().isoformat()},
                       indent=2),
            encoding="utf-8"
        )

    def save(self, content: str, category: str = "general", importance: int = 2):
        entry = {
            "id":         str(uuid.uuid4())[:8],
            "content":    content,
            "category":   category,
            "importance": importance,
            "created":    datetime.utcnow().isoformat(),
        }
        self._entries.append(entry)
        self._save()
        return entry["id"]

    def search(self, query: str, limit: int = 5) -> list[str]:
        """Simple keyword search. Returns list of content strings."""
        words = set(re.findall(r"\w+", query.lower()))
        if not words:
            return []
        scored = []
        for e in self._entries:
            text  = e.get("content", "").lower()
            score = sum(1 for w in words if w in text)
            if score:
                scored.append((score * e.get("importance", 1), e["content"]))
        scored.sort(reverse=True)
        return [c for _, c in scored[:limit]]

    def auto_save(self, user_text: str, response_text: str):
        """Let the agent decide what to remember — basic heuristics."""
        # Save if user explicitly tells us to remember something
        triggers = ["remember", "note that", "don't forget", "keep in mind", "my name", "i am", "i work"]
        text_lower = user_text.lower()
        if any(t in text_lower for t in triggers):
            self.save(f"User said: {user_text}", category="preference", importance=3)

    def sync(self):
        self._save()
        # GitHub Gist sync if configured
        if self.settings.memory_backend == "gist" and self.settings.github_token:
            self._sync_gist()

    def _sync_gist(self):
        try:
            import requests
            content = MEMORY_FILE.read_text(encoding="utf-8")
            headers = {"Authorization": f"token {self.settings.github_token}"}
            data = {"files": {"vnsa_memory.json": {"content": content}}}
            if self.settings.gist_id:
                requests.patch(
                    f"https://api.github.com/gists/{self.settings.gist_id}",
                    json=data, headers=headers, timeout=10
                )
            else:
                r = requests.post(
                    "https://api.github.com/gists",
                    json={**data, "public": False,
                          "description": "VNSA Memory"},
                    headers=headers, timeout=10
                )
                self.settings.gist_id = r.json().get("id", "")
        except Exception as e:
            print(f"[Memory] Gist sync error: {e}")
