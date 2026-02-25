from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agents.tools.KaliMCP import KaliMCP
from agents.helpers.save_json import extract_json_from_llm_response


def _load_prompt() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "execute_agent_prompt.txt"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@dataclass
class ExecuteResult:
    success:        bool
    output_summary: str  = ""
    key_facts:      list = field(default_factory=list)  # list of dicts
    raw_output:     str  = ""
    error:          Optional[str] = None


class ExecuteAgent:
    def __init__(self, llm):
        self.llm  = llm
        self.kali = KaliMCP()

    async def run(self,
                  target_url: str,
                  task: str,
                  allowed_tools: Optional[list] = None,
                  context: str = "") -> ExecuteResult:
        tools_str   = ", ".join(allowed_tools) if allowed_tools else "curl, sqlmap, hydra, wfuzz, python3"
        context_str = f"Context from coordinator:\n{context}" if context else ""

        prompt = (
            _load_prompt()
            .replace("__TARGET_URL__",    target_url)
            .replace("__TASK__",          task)
            .replace("__ALLOWED_TOOLS__", tools_str)
            .replace("__CONTEXT__",       context_str)
        )

        try:
            result = await self.kali._call(self.llm, prompt)
        except Exception as e:
            print(f"[ExecuteAgent] KaliMCP call failed: {e}")
            return ExecuteResult(success=False, error=str(e))

        raw_text = self._extract_last_message(result)
        if not raw_text:
            return ExecuteResult(success=False, error="No response from execute agent")

        return self._parse(raw_text)

    def _extract_last_message(self, result: dict) -> str:
        sr = result.get("structured_response")
        if sr and hasattr(sr, "output"):
            return sr.output

        messages = result.get("messages", [])
        if not messages:
            return ""
        last = messages[-1]
        if hasattr(last, "content"):
            return last.content
        return str(last)

    def _parse(self, raw_text: str) -> ExecuteResult:
        try:
            data = extract_json_from_llm_response(raw_text)
        except Exception as e:
            print(f"[ExecuteAgent] JSON parse failed: {e}")
            return ExecuteResult(success=False, raw_output=raw_text, error=f"JSON parse failed: {e}")

        if not isinstance(data, dict) or "success" not in data:
            print(f"[ExecuteAgent] Unexpected response shape: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            return ExecuteResult(success=False, raw_output=raw_text, error="Missing 'success' key in response")

        key_facts = []
        for kf in data.get("key_facts", []):
            if not isinstance(kf, dict) or not kf.get("fact"):
                continue
            key_facts.append({
                "fact":         kf.get("fact", ""),
                "significance": kf.get("significance", ""),
            })

        return ExecuteResult(
            success=bool(data.get("success", False)),
            output_summary=data.get("output_summary", ""),
            key_facts=key_facts,
            raw_output=data.get("raw_output", ""),
        )
