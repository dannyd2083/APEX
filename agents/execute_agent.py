from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agents.tools.KaliMCP import KaliMCP
from agents.helpers.save_json import extract_json_from_llm_response


def _load(name: str) -> str:
    path = Path(__file__).resolve().parent / "prompts" / name
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _trim_output(raw: str, head: int = 3000, tail: int = 6000) -> str:
    """Keep first N + last M chars so results (always at end) are never cut off."""
    if len(raw) <= head + tail:
        return raw
    return raw[:head] + "\n...[middle truncated]...\n" + raw[-tail:]


def _extract_script(text: str) -> str:
    """Strip markdown fences if the LLM wrapped the script in them."""
    for pattern in [
        r"```(?:bash|sh)?\s*\r?\n(.*?)```",   # standard fence, optional \r
        r"`{3,}(?:bash|sh)?\s*\r?\n(.*?)`{3,}", # 3+ backticks
        r"```(?:bash|sh)?(.*?)```",             # no newline after language tag
    ]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            return m.group(1).strip()
    return text.strip()


def _extract_exit_code(raw_output: str) -> Optional[int]:
    """Parse exit code from KaliMCP output format: [exit code: N]"""
    m = re.search(r"\[exit code:\s*(\d+)\]", raw_output)
    return int(m.group(1)) if m else None


_SUCCESS_PATTERNS = [
    r"rows dumped",
    r"\[\d+\] entr",        # sqlmap "[N] entries"
    r"fetched data logged",
    r"Database:\s+\w",
    r"\|\s+\w.*\|\s+\w",    # ASCII table row (sqlmap dump)
    r"uid=\d+\(",           # RCE: uid=0(root)
    r"session\s+\d+\s+opened",
    r"Login succeeded",
    r"HTTP/\S+\s+302",      # redirect after POST login
    r"password\s*[:=]\s*\S",  # found credential
]

def _infer_success_from_output(raw: str) -> bool:
    """Heuristic fallback when LLM JSON is unparseable."""
    for p in _SUCCESS_PATTERNS:
        if re.search(p, raw, re.IGNORECASE):
            return True
    return False


@dataclass
class ExecuteResult:
    success:        bool
    output_summary: str  = ""
    key_facts:      list = field(default_factory=list)
    raw_output:     str  = ""
    error:          Optional[str] = None
    script:         str  = ""   # the bash script that was generated and run


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

        # ── Call 1: ask LLM to write the bash script ──────────────────────
        script_prompt = (
            _load("execute_script_prompt.txt")
            .replace("__TARGET_URL__",    target_url)
            .replace("__TASK__",          task)
            .replace("__ALLOWED_TOOLS__", tools_str)
            .replace("__CONTEXT__",       context_str)
        )
        script_text = self.llm._call(script_prompt, phase="execute_plan")
        script = _extract_script(script_text)

        if not script:
            return ExecuteResult(success=False, error="LLM produced no script")

        print(f"[ExecuteAgent] Script:\n{script[:400]}")

        # ── Execute on Kali — with self-healing retry ──────────────────────
        MAX_FIX_ATTEMPTS = 2
        raw_output = ""
        for attempt in range(MAX_FIX_ATTEMPTS + 1):
            try:
                raw_output = await self.kali.execute(script)
            except Exception as e:
                return ExecuteResult(success=False, error=f"Kali execution failed: {e}")

            exit_code = _extract_exit_code(raw_output)
            print(f"[ExecuteAgent] Attempt {attempt+1} — exit code: {exit_code}")

            # Exit 0 or unknown exit code → don't retry
            if exit_code == 0 or exit_code is None or attempt == MAX_FIX_ATTEMPTS:
                break

            # Only fix on actual shell errors — not logical failures (grep no match, curl 4xx, etc.)
            stderr_m = re.search(r'\[stderr\](.*?)(?:\[stdout\]|\[exit code|$)', raw_output, re.DOTALL)
            stderr   = stderr_m.group(1).strip() if stderr_m else ""
            if not re.search(r'syntax error|command not found|unexpected token|unbound variable|No such file', stderr, re.IGNORECASE):
                break  # logical failure — let interpret handle it

            # Shell syntax/command error → ask LLM to fix
            print(f"[ExecuteAgent] Script failed (exit {exit_code}), asking LLM to fix...")
            fix_prompt = (
                f"The bash script below failed with exit code {exit_code}.\n\n"
                f"Script:\n```bash\n{script}\n```\n\n"
                f"Error output:\n{raw_output[:1000]}\n\n"
                f"Fix the syntax or command error. Output ONLY the corrected bash script, no explanation."
            )
            fixed = self.llm._call(fix_prompt, phase="execute_fix")
            script = _extract_script(fixed) or script

        print(f"[ExecuteAgent] Output: {raw_output[:300]}")

        # ── Call 2: interpret the output ───────────────────────────────────
        interpret_prompt = (
            _load("execute_interpret_prompt.txt")
            .replace("__TASK__",   task)
            .replace("__OUTPUT__", _trim_output(raw_output))
        )
        response = self.llm._call(interpret_prompt, phase="execute_interpret", json_mode=True)
        result = self._parse(response, raw_output)
        result.script = script
        return result

    def _parse(self, raw_text: str, raw_output: str = "") -> ExecuteResult:
        try:
            data = json.loads(raw_text)
        except Exception as e:
            inferred = _infer_success_from_output(raw_output)
            return ExecuteResult(
                success=inferred,
                raw_output=raw_output[:1000],
                output_summary="(JSON parse failed — inferred from raw output)",
                error=f"JSON parse failed: {e}",
            )

        if not isinstance(data, dict) or "success" not in data:
            inferred = _infer_success_from_output(raw_output)
            return ExecuteResult(
                success=inferred,
                raw_output=raw_output[:1000],
                output_summary="(Missing success key — inferred from raw output)",
                error="Missing 'success' key in response",
            )

        key_facts = [
            {"fact": kf.get("fact", ""), "significance": kf.get("significance", "")}
            for kf in data.get("key_facts", [])
            if isinstance(kf, dict) and kf.get("fact")
        ]

        return ExecuteResult(
            success=bool(data.get("success", False)),
            output_summary=data.get("output_summary", ""),
            key_facts=key_facts,
            raw_output=data.get("raw_output", raw_output[:1000]),
        )
