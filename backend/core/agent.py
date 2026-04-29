"""VNSA 2.0 — Agent v2. Supports file attachment content."""
import json
import importlib.util
from datetime import datetime
from pathlib import Path
from typing import Optional
import anthropic

TOOLS_DIR = Path(__file__).parent.parent / "tools"

LENS_PROMPT = """You are VNSA watching this screen for {user_name}.
Give ONE short actionable insight — something {user_name} does NOT already know.

NEVER describe what is visible. ONLY speak up for:
- Risks, errors, conflicts, missed steps, smarter approaches, urgency

If nothing genuinely useful: reply SILENT

Format exactly:
CATEGORY: suggestion|warning|action|info|reminder
INSIGHT: <direct advice, max 2 sentences>"""


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

    def chat(self, user_text: str) -> str:
        """Standard text chat."""
        return self.chat_with_content([{"type": "text", "text": user_text}])

    def chat_with_content(self, content: list) -> str:
        """Chat with arbitrary content (text + images + file text)."""
        mem_ctx = self.memory.search(
            " ".join(p.get("text", "") for p in content if p.get("type") == "text"),
            limit=5
        )
        system = self._build_system(mem_ctx)

        # Add to history as user turn
        self.history.append({"role": "user", "content": content})
        history = self.history[-20:]

        try:
            response = self.client.messages.create(
                model=self.settings.claude_model,
                max_tokens=1500,
                system=system,
                tools=self.tools if self.tools else anthropic.NOT_GIVEN,
                messages=history,
            )
        except Exception as e:
            return f"I'm having trouble reaching my brain right now — {e}"

        # Tool use loop
        while response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = self._run_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    })
            history.append({"role": "assistant", "content": response.content})
            history.append({"role": "user",      "content": tool_results})
            try:
                response = self.client.messages.create(
                    model=self.settings.claude_model,
                    max_tokens=1500,
                    system=system,
                    tools=self.tools if self.tools else anthropic.NOT_GIVEN,
                    messages=history,
                )
            except Exception as e:
                return f"Tool execution error — {e}"

        text = "".join(b.text for b in response.content if hasattr(b, "text"))

        # Save assistant turn to history
        self.history.append({"role": "assistant", "content": text})

        # Auto-save memory
        user_text = " ".join(
            p.get("text", "") for p in content if p.get("type") == "text"
        )
        self.memory.auto_save(user_text, text)

        return text.strip()

    def _run_tool(self, name: str, inputs: dict) -> str:
        handler = self.handlers.get(name)
        if not handler:
            return f"Tool '{name}' not found"
        try:
            return handler(**inputs)
        except Exception as e:
            return f"Tool error ({name}): {e}"

    def _build_system(self, memory_context: list) -> str:
        parts = [self.settings.persona]
        parts.append(f"\nCurrent time: {datetime.now().strftime('%A %d %B %Y, %H:%M')}")
        parts.append(f"Current mode: {self.mode}")
        if memory_context:
            parts.append("\nRelevant memories:\n" +
                         "\n".join(f"- {e}" for e in memory_context))
        return "\n".join(parts)

    def analyse_screen(self, img_b64: str) -> Optional[dict]:
        try:
            prompt = LENS_PROMPT.format(user_name=self.settings.user_name)
            msg = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image",
                         "source": {"type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": img_b64}},
                        {"type": "text", "text": prompt}
                    ]
                }]
            )
            raw = msg.content[0].text.strip()
            return self._parse_lens(raw)
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
        if "idle" in insight.lower():
            return None
        return {"category": cat, "insight": insight,
                "time": datetime.now().strftime("%H:%M:%S")}
