"""VNSA 2.0 — Agent v4
- max_tokens raised to 4096 (complex tasks won't be truncated)
- Tool output cap raised to 8000 chars
- Tool loop increased to 10 iterations
- Rate-limit fallback: trim history first, drop to Haiku only as last resort
- Memory search: top 5 results, longer snippets
"""
import importlib.util
from datetime import datetime
from pathlib import Path
from typing import Optional
import anthropic

TOOLS_DIR  = Path(__file__).parent.parent / "tools"
LENS_MODEL = "claude-haiku-4-5-20251001"

# Response token budget — high enough for complex multi-step answers
_TOKENS_MAIN  = 4096   # regular chat + tool continuation
_TOKENS_LENS  = 100    # screen analysis (kept tiny intentionally)

LENS_PROMPT = """You are VNSA watching this screen.
Give ONE short actionable insight the user doesn't already know.
NEVER describe what is visible. Only flag: risks, errors, conflicts, urgent items.
If nothing useful: reply SILENT
Format:
CATEGORY: suggestion|warning|action|info|reminder
INSIGHT: <max 2 sentences>"""


class VNSAAgent:
    def __init__(self, settings, memory):
        self.settings = settings
        self.memory   = memory
        self.mode     = settings.mode
        self.client   = anthropic.Anthropic(api_key=settings.anthropic_key)
        self.history  = []
        self.tools    = []
        self.handlers = {}
        self._load_tools()

    # ── Tool loading ──────────────────────────────────────────────────────────

    def _load_tools(self):
        if not TOOLS_DIR.exists():
            return
        for f in sorted(TOOLS_DIR.glob("*.py")):
            if f.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"tools.{f.stem}", f)
                mod  = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "TOOL_DEFINITION") and hasattr(mod, "run"):
                    self.tools.append(mod.TOOL_DEFINITION)
                    self.handlers[mod.TOOL_DEFINITION["name"]] = mod.run
                    print(f"[Agent] Tool loaded: {mod.TOOL_DEFINITION['name']}")
            except Exception as e:
                print(f"[Agent] Tool load failed {f.name}: {e}")
        print(f"[Agent] {len(self.tools)} tools active")

    # ── Chat ──────────────────────────────────────────────────────────────────

    def chat(self, user_text: str) -> str:
        return self.chat_with_content([{"type": "text", "text": user_text}])

    def chat_with_content(self, content: list) -> str:
        user_text = " ".join(
            p.get("text", "") for p in content if p.get("type") == "text"
        )

        # Memory — top 5 results, slightly longer snippets
        mem_ctx = self.memory.search(user_text, limit=5)
        system  = self._build_system(mem_ctx)

        # Keep last 20 messages (10 conversation turns) for context
        if len(self.history) > 20:
            self.history = self.history[-20:]

        self.history.append({"role": "user", "content": content})
        history = list(self.history)

        # ── Initial API call ──────────────────────────────────────────────────
        try:
            response = self._call_api(system, history, self.settings.claude_model, _TOKENS_MAIN)

        except anthropic.RateLimitError:
            print("[Agent] Rate limit hit — trimming history and retrying")
            # First retry: same model, minimal history (last 4 messages)
            trimmed = self.history[-4:]
            try:
                response = self._call_api(system, trimmed, self.settings.claude_model, _TOKENS_MAIN)
            except anthropic.RateLimitError:
                # Last resort: Haiku with 2 messages — preserve some intelligence
                print("[Agent] Still rate-limited — falling back to Haiku")
                try:
                    response = self._call_api(
                        self._build_system([]),
                        self.history[-2:],
                        "claude-haiku-4-5-20251001",
                        2048,
                    )
                except Exception as e3:
                    return f"I'm currently rate-limited — please wait a moment. ({e3})"
            except Exception as e2:
                return f"Connection error — {e2}"

        except Exception as e:
            return f"Connection error — {e}"

        # ── Agentic tool loop ─────────────────────────────────────────────────
        loops = 0
        while response.stop_reason == "tool_use" and loops < 10:
            loops += 1
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    out = self._run_tool(block.name, block.input)
                    results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        # Raised from 1500 → 8000 so tools like web search / file read can return full content
                        "content":     str(out)[:8000],
                    })

            history.append({"role": "assistant", "content": response.content})
            history.append({"role": "user",      "content": results})

            # Keep tool-loop history manageable
            if len(history) > 20:
                history = history[-20:]

            try:
                response = self._call_api(system, history, self.settings.claude_model, _TOKENS_MAIN)
            except anthropic.RateLimitError:
                # On rate limit mid-tool-loop, return what we have so far
                partial = "".join(b.text for b in response.content if hasattr(b, "text"))
                if partial:
                    return partial.strip() + "\n\n*(Rate limit hit — some steps may be incomplete.)*"
                return "Rate limit hit during tool execution — please retry."
            except Exception as e:
                return f"Tool loop error — {e}"

        # ── Extract final text ────────────────────────────────────────────────
        text = "".join(b.text for b in response.content if hasattr(b, "text"))

        # Persist conversation history (last 20 messages = 10 turns)
        self.history.append({"role": "assistant", "content": text})
        if len(self.history) > 20:
            self.history = self.history[-20:]

        self.memory.auto_save(user_text, text)
        return text.strip()

    # ── API call wrapper ──────────────────────────────────────────────────────

    def _call_api(self, system: str, history: list, model: str, max_tokens: int):
        return self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=self.tools if self.tools else anthropic.NOT_GIVEN,
            messages=history,
        )

    def _run_tool(self, name: str, inputs: dict) -> str:
        handler = self.handlers.get(name)
        if not handler:
            return f"Tool '{name}' not found."
        try:
            return handler(**inputs)
        except Exception as e:
            return f"Tool error ({name}): {e}"

    # ── System prompt ─────────────────────────────────────────────────────────

    def _build_system(self, memory_context: list) -> str:
        """Compact system prompt — rich enough for intelligence, short enough to save tokens."""
        parts = [self.settings.persona]
        parts.append(f"Time: {datetime.now().strftime('%a %d %b %Y %H:%M')}")
        parts.append(f"Mode: {self.mode}")
        if memory_context:
            # Allow slightly longer memory snippets (150 chars each)
            short = [m[:150] for m in memory_context[:5]]
            parts.append("Memory:\n" + "\n".join(f"- {m}" for m in short))
        return "\n".join(parts)

    # ── Screen / Lens analysis ────────────────────────────────────────────────

    def analyse_screen(self, img_b64: str) -> Optional[dict]:
        try:
            msg = self.client.messages.create(
                model=LENS_MODEL,
                max_tokens=_TOKENS_LENS,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64",
                     "media_type": "image/jpeg", "data": img_b64}},
                    {"type": "text", "text": LENS_PROMPT},
                ]}],
            )
            return self._parse_lens(msg.content[0].text.strip())
        except Exception as e:
            print(f"[Agent] Lens error: {e}")
            return None

    @staticmethod
    def _parse_lens(raw: str) -> Optional[dict]:
        if not raw or "SILENT" in raw.upper():
            return None
        cat     = "info"
        insight = raw
        for line in raw.splitlines():
            if line.upper().startswith("CATEGORY:"):
                cat = line.split(":", 1)[1].strip().lower()
            elif line.upper().startswith("INSIGHT:"):
                insight = line.split(":", 1)[1].strip()
        return {"category": cat, "insight": insight,
                "time": datetime.now().strftime("%H:%M:%S")}
