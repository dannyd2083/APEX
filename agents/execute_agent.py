from __future__ import annotations

import json
import re  # used in _extract_script, _extract_exit_code
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agents.tools.KaliMCP import KaliMCP


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


@dataclass
class ExecuteResult:
    success:        bool
    output_summary: str  = ""
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

        # Safety: | head closes the pipe early → SIGPIPE kills any tool before results appear.
        # Replace ALL | head occurrences with | cat. execute_agent already trims long output.
        script = re.sub(r"\|\s*head\b[^\n]*", "| cat", script)

        # Safety: grep -P / grep -oP (Perl regex) silently produces empty output on Kali
        # when \K lookahead is used — exit code 0, no stderr, but TOKEN is empty.
        # The self-healing loop won't catch this (no shell error). Intercept here instead.
        if re.search(r'\bgrep\s+["\']?-[a-zA-Z]*P', script):
            print("[ExecuteAgent] grep -P/-oP detected — asking LLM to rewrite with POSIX grep...")
            fix_prompt = (
                "The bash script below uses 'grep -P' or 'grep -oP' (Perl regex) which silently "
                "fails on Kali Linux — it produces empty output with exit code 0.\n"
                "Replace ALL grep -P and grep -oP patterns with POSIX-compatible grep -o.\n"
                "For _token extraction from HTML, use this exact pattern:\n"
                "  TOKEN=$(echo \"$PAGE\" | tr \"'\" '\"' | grep -o 'name=\"_token\"[^>]*>' "
                "| grep -o 'value=\"[^\"]*\"' | cut -d'\"' -f2 || true)\n"
                "Output ONLY the corrected bash script, no explanation.\n\n"
                f"Script:\n{script}"
            )
            fixed = self.llm._call(fix_prompt, phase="execute_fix")
            script = _extract_script(fixed) or script
            print("[ExecuteAgent] grep -P fix applied")

        print(f"[ExecuteAgent] Script:\n{script[:400]}")

        # Pre-run cleanup: kill lingering sqlmap processes from previous turns.
        # Runs as a SEPARATE call so the cleanup bash process's own cmdline does not
        # contain the literal string /usr/bin/sqlmap — the [/] bracket trick prevents
        # the awk pattern from matching its own cmdline, avoiding self-kill (exit -15).
        cleanup_cmd = (
            "MYPID=$$; "
            "kill $(ps aux | awk -v m=$MYPID "
            "'/[/]usr[/]bin[/]sqlmap/ && $2!=m {print $2}') "
            "2>/dev/null; sleep 1; true"
        )
        try:
            await self.kali.execute(cleanup_cmd)
        except Exception:
            pass  # cleanup failure is non-fatal

        # ── Execute on Kali — with self-healing retry ──────────────────────
        MAX_FIX_ATTEMPTS = 2
        raw_output = ""
        for attempt in range(MAX_FIX_ATTEMPTS + 1):
            try:
                raw_output = await self.kali.execute(script)
            except BaseException as e:
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
            return ExecuteResult(
                success=False,
                raw_output=raw_output[:1000],
                output_summary="(JSON parse failed)",
                error=f"JSON parse failed: {e}",
            )

        if not isinstance(data, dict):
            return ExecuteResult(
                success=False,
                raw_output=raw_output[:1000],
                output_summary="(Invalid JSON response)",
                error="Response is not a JSON object",
            )

        # success is always False here — coordinator judges success from full context
        head, tail = 5_000, 15_000
        if len(raw_output) <= head + tail:
            trimmed = raw_output
        else:
            trimmed = raw_output[:head] + "\n...[middle truncated]...\n" + raw_output[-tail:]
        return ExecuteResult(
            success=False,
            output_summary=data.get("output_summary", ""),
            raw_output=trimmed,
        )
