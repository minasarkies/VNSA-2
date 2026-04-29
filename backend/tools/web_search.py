"""VNSA 2.0 — Web search via Perplexity."""
import requests
from pathlib import Path

TOOL_DEFINITION = {
    "name": "web_search",
    "description": "Search the web for current information.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"}
        },
        "required": ["query"],
    },
}


def run(query: str) -> str:
    key = _get_key()
    if not key:
        return "Web search unavailable — PERPLEXITY_API_KEY not set in keys.env."
    try:
        r = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "sonar",
                "messages": [{"role": "user", "content": query}],
                "max_tokens": 500,
            },
            timeout=15,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Search error: {e}"


def _get_key() -> str:
    import os
    key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not key:
        from dotenv import load_dotenv
        keys = Path(__file__).parent.parent / "config" / "keys.env"
        if keys.exists():
            load_dotenv(keys, encoding="utf-8-sig")
            key = os.environ.get("PERPLEXITY_API_KEY", "")
    return key if key and "YOUR" not in key else ""
