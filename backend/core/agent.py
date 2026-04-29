"""VNSA 2.0 — Agent v3. Reduced token usage to stay within rate limits."""
import importlib.util
from datetime import datetime
from pathlib import Path
from typing import Optional
import anthropic

TOOLS_DIR = Path(__file__).parent.parent / "tools"
LENS_MODEL = "claude-haiku-4-5-20251001"

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

    def _load_tools(self):
        if not TOOLS_DIR.exists():
            return
        for f in TOOLS_DIR.glob("*.py"):
            if f.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"tools.{f.stem}", f)
                mod  = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "TOOL_DEFINITION") and hasattr(mod, "run"):
                    self.tools.append(mod.TOOL_DEFINITION)
                    self.handlers[mod.TOOL_DEFINITION["name"]] = mod.run
                    print(f"[Agent] Tool: {mod.TOOL_DEFINITION['name']}")
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

        # Only top 3 short memory results
        mem_ctx = self.memory.search(user_text, limit=3)
        system  = self._build_system(mem_ctx)

        # Hard cap: last 10 messages only
        if len(self.history) > 10:
            self.history = self.history[-10:]

        self.history.append({"role": "user", "content": content})
        history = list(self.history)

        try:
            response = self._call_api(system, history, self.settings.claude_model, 1024)
        except anthropic.RateLimitError:
            # Trim history aggressively and retry with Haiku
            print("[Agent] Rate limit — retrying with trimmed history on Haiku")
            self.history = self.history[-2:]
            history = list(self.history)
            try:
                response = self._call_api(
                    self._build_system([]),  # no memory on retry
                    history,
                    "claude-haiku-4-5-20251001",
                    512
                )
            except Exception as e2:
                return f"I hit my rate limit — please wait a moment and try again. ({e2})"
        except Exception as e:
            return f"Connection error — {e}"

        # Tool loop
        loops = 0
        while response.stop_reason == "tool_use" and loops < 5:
            loops += 1
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    out = self._run_tool(block.name, block.input)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(out)[:1500],  # cap tool output
                    })
            history.append({"role": "assistant", "content": response.content})
            history.append({"role": "user",      "content": results})
            if len(history) > 14:
                history = history[-14:]
            try:
                response = self._call_api(system, history, self.settings.claude_model, 1024)
            except Exception as e:
                return f"Tool error — {e}"

        text = "".join(b.text for b in response.content if hasattr(b, "text"))

        self.history.append({"role": "assistant", "content": text})
        if len(self.history) > 10:
            self.history = self.history[-10:]

        self.memory.auto_save(user_text, text)
        return text.strip()

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
            return f"Tool '{name}' not found"
        try:
            return handler(**inputs)
        except Exception as e:
            return f"Tool error ({name}): {e}"

    def _build_system(self, memory_context: list) -> str:
        """Concise system prompt — kept short to save tokens."""
        parts = [self.settings.persona]
        parts.append(f"Time: {datetime.now().strftime('%a %d %b %Y %H:%M')}")
        parts.append(f"Mode: {self.mode}")
        if memory_context:
            short = [m[:100] for m in memory_context[:3]]
            parts.append("Memory:\n" + "\n".join(f"- {m}" for m in short))
        return "\n".join(parts)

    # ── Screen analysis ───────────────────────────────────────────────────────

    def analyse_screen(self, img_b64: str) -> Optional[dict]:
        try:
            msg = self.client.messages.create(
                model=LENS_MODEL,
                max_tokens=100,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64",
                     "media_type": "image/jpeg", "data": img_b64}},
                    {"type": "text", "text": LENS_PROMPT}
                ]}]
            )
            return self._parse_lens(msg.content[0].text.strip())
        except Exception as e:
            print(f"[Agent] Lens error: {e}")
            return None

    @staticmethod
    def _parse_lens(raw: str) -> Optional[dict]:
        if not raw or "SILENT" in raw.upper():
            return None
        cat = "info"; insight = raw
        for line in raw.splitlines():
            if line.upper().startswith("CATEGORY:"):
                cat = line.split(":", 1)[1].strip().lower()
            elif line.upper().startswith("INSIGHT:"):
                insight = line.split(":", 1)[1].strip()
        return {"category": cat, "insight": insight,
                "time": datetime.now().strftime("%H:%M:%S")}
