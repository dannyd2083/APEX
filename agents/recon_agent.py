from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agents.tools.KaliMCP import KaliMCP
from agents.helpers.save_json import extract_json_from_llm_response


def _load_prompt() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "recon_agent_prompt.txt"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@dataclass
class ReconResult:
    findings:    list = field(default_factory=list)   # list of dicts
    hypotheses:  list = field(default_factory=list)   # list of dicts
    dead_ends:   list = field(default_factory=list)   # list of strings
    raw_summary: str  = ""
    error:       Optional[str] = None                 # set if recon failed


class ReconAgent:
    def __init__(self, llm):
        self.llm  = llm
        self.kali = KaliMCP()

    async def run(self,
                  target_url: str,
                  objective: str,
                  allowed_tools: Optional[list] = None,
                  context: str = "") -> ReconResult:
        """
        Run a focused recon task and return structured findings.

        Args:
            target_url:    The URL to investigate (e.g. "http://10.x.x.x/")
            objective:     What to find (e.g. "enumerate web directories")
            allowed_tools: Which tools the agent may use. None = all available.
            context:       Any prior findings the agent should know about.

        Returns:
            ReconResult with findings, hypotheses, dead_ends, raw_summary.
        """
        tools_str   = ", ".join(allowed_tools) if allowed_tools else "nmap, gobuster, curl, nikto, zap-cli"
        context_str = f"Context from previous steps:\n{context}" if context else ""

        prompt = (
            _load_prompt()
            .replace("__TARGET_URL__",    target_url)
            .replace("__OBJECTIVE__",     objective)
            .replace("__ALLOWED_TOOLS__", tools_str)
            .replace("__CONTEXT__",       context_str)
        )

        try:
            result = await self.kali._call(self.llm, prompt)
        except Exception as e:
            print(f"[ReconAgent] KaliMCP call failed: {e}")
            return ReconResult(error=str(e))

        # Extract the final agent message
        raw_text = self._extract_last_message(result)
        if not raw_text:
            return ReconResult(error="No response from recon agent")

        return self._parse(raw_text)

    def _extract_last_message(self, result: dict) -> str:
        messages = result.get("messages", [])
        if not messages:
            return ""
        last = messages[-1]
        if hasattr(last, "content"):
            return last.content
        return str(last)

    def _parse(self, raw_text: str) -> ReconResult:
        """Parse the agent's JSON response into a ReconResult."""
        try:
            data = extract_json_from_llm_response(raw_text)
        except Exception as e:
            print(f"[ReconAgent] JSON parse failed: {e}")
            print(f"[ReconAgent] Raw response: {raw_text[:500]}")
            return ReconResult(raw_summary=raw_text, error=f"JSON parse failed: {e}")

        if not isinstance(data, dict) or "findings" not in data:
            print(f"[ReconAgent] Unexpected response shape: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            return ReconResult(raw_summary=raw_text, error="Missing 'findings' key in response")

        # Validate and normalise each finding
        findings = []
        for f in data.get("findings", []):
            if not isinstance(f, dict):
                continue
            if not f.get("type") or not f.get("value"):
                continue
            findings.append({
                "type":       f.get("type", "unknown"),
                "value":      f.get("value", ""),
                "confidence": f.get("confidence", "medium"),
                "evidence":   f.get("evidence", ""),
            })

        # Validate hypotheses
        hypotheses = []
        for h in data.get("hypotheses", []):
            if not isinstance(h, dict):
                continue
            if not h.get("description"):
                continue
            hypotheses.append({
                "description": h.get("description", ""),
                "confidence":  float(h.get("confidence", 0.5)),
            })

        return ReconResult(
            findings=findings,
            hypotheses=hypotheses,
            dead_ends=data.get("dead_ends", []),
            raw_summary=data.get("raw_summary", ""),
        )
