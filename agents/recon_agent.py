from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from agents.tools.KaliMCP import KaliMCP
from agents.helpers.save_json import extract_json_from_llm_response
from agents.helpers.output_parsers import (
    parse_nmap, parse_gobuster, parse_zap_alerts, parse_zap_spider, parse_autorecon,
)


def _load(name: str) -> str:
    path = Path(__file__).resolve().parent / "prompts" / name
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _extract_script(text: str) -> str:
    """Strip markdown fences if the LLM wrapped the script in them."""
    for pattern in [
        r"```(?:bash|sh)?\s*\r?\n(.*?)```",
        r"`{3,}(?:bash|sh)?\s*\r?\n(.*?)`{3,}",
        r"```(?:bash|sh)?(.*?)```",
    ]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            return m.group(1).strip()
    return text.strip()


def _trim_output(raw: str, head: int = 40000, tail: int = 4000) -> str:
    """Keep first N + last M chars so results (always at end) are never cut off."""
    if len(raw) <= head + tail:
        return raw
    return raw[:head] + "\n...[middle truncated]...\n" + raw[-tail:]


def _extract_exit_code(raw_output: str) -> Optional[int]:
    """Parse exit code from KaliMCP output format: [exit code: N]"""
    m = re.search(r"\[exit code:\s*(\d+)\]", raw_output)
    return int(m.group(1)) if m else None


# Tools handled by named MCP methods
_NAMED_TOOLS = {"nmap", "gobuster", "zap-spider", "zap-active", "sqlmap", "autorecon"}

# Tools whose output is structured — parsed by code, no LLM needed
_PARSED_TOOLS = {"nmap", "gobuster", "zap-spider", "zap-active", "autorecon"}


@dataclass
class ReconResult:
    findings:    list = field(default_factory=list)
    dead_ends:   list = field(default_factory=list)
    raw_summary: str  = ""
    error:       Optional[str] = None
    script:      str  = ""   # the bash script that was generated and run (or tool label)
    raw_output:  str  = ""   # raw stdout/stderr from Kali


class ReconAgent:
    def __init__(self, llm):
        self.llm  = llm
        self.kali = KaliMCP()

    async def run(self,
                  target_url: str,
                  objective: str,
                  allowed_tools: Optional[list] = None,
                  context: str = "",
                  goal: str = "shell") -> ReconResult:

        primary_tool = (allowed_tools or ["curl"])[0].lower()

        if primary_tool in _NAMED_TOOLS:
            # ── Named MCP tool path — no bash script generation ────────────
            print(f"[ReconAgent] Using named MCP tool: {primary_tool}")
            try:
                raw_output = await self._run_named_tool(primary_tool, target_url)
            except BaseException as e:
                return ReconResult(error=f"Named tool '{primary_tool}' failed: {e}")
            script = f"# {primary_tool} via named MCP tool"
        else:
            # ── Bash script fallback (curl, nikto, complex tasks) ──────────
            script, raw_output = await self._run_bash_script(
                target_url, objective, allowed_tools, context
            )
            if raw_output.startswith("ERROR:"):
                return ReconResult(error=raw_output, script=script)

        print(f"[ReconAgent] Output ({primary_tool}): {raw_output[:300]}")

        # ── Structured tools: code parser ─────────────────────────────────
        if primary_tool in _PARSED_TOOLS:
            result = self._parse_structured(primary_tool, raw_output)
            result.script     = script
            result.raw_output = raw_output
            print(f"[ReconAgent] Code-parsed {len(result.findings)} findings")
            return result

        # ── Unstructured tools: LLM interpret (curl, nikto, sqlmap, etc.) ─
        interpret_prompt = (
            _load("recon_interpret_prompt.txt")
            .replace("__OBJECTIVE__", objective)
            .replace("__OUTPUT__",    _trim_output(raw_output))
        )
        response = self.llm._call(interpret_prompt, phase="recon_interpret", json_mode=True)
        result = self._parse(response)
        result.script     = script
        result.raw_output = raw_output
        return result

    # ------------------------------------------------------------------
    # Named tool dispatch
    # ------------------------------------------------------------------

    async def _run_named_tool(self, tool: str, target_url: str) -> str:
        if tool == "nmap":
            parsed = urlparse(target_url)
            target = parsed.hostname or target_url
            ports  = str(parsed.port) if parsed.port else ""
            return await self.kali.nmap_scan(target, ports=ports)
        elif tool == "gobuster":
            return await self.kali.gobuster_scan(await self._resolve_vhost(target_url))
        elif tool == "zap-spider":
            return await self.kali.zap_spider(target_url)
        elif tool == "zap-active":
            return await self.kali.zap_active(target_url)
        elif tool == "sqlmap":
            return await self.kali.sqlmap(target_url)
        elif tool == "autorecon":
            parsed = urlparse(target_url)
            target = parsed.hostname or target_url
            import asyncio
            for attempt in range(3):
                raw = await self.kali.autorecon(target)
                exit_code = _extract_exit_code(raw)
                # exit_code None = "?" = HTTP connection failure, retry
                if exit_code is not None:
                    return raw
                print(f"[ReconAgent] autorecon connection failure (attempt {attempt+1}/3), retrying in 5s...")
                await asyncio.sleep(5)
            return raw  # return last attempt regardless
        return f"(unknown named tool: {tool})"

    # ------------------------------------------------------------------
    # Bash script fallback
    # ------------------------------------------------------------------

    async def _resolve_vhost(self, url: str) -> str:
        """If url uses a bare IP, check Kali /etc/hosts for a hostname and return hostname URL."""
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
            return url  # already a hostname
        raw = await self.kali.execute(f"grep -m1 '^{host}' /etc/hosts")
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("["):
                continue  # skip KaliMCP metadata lines ([exit code:], [stdout], etc.)
            parts = line.split()
            if len(parts) >= 2 and parts[0] == host:
                hostname = parts[1]
                new_url = url.replace(host, hostname, 1)
                print(f"[ReconAgent] vhost resolved: {url} -> {new_url}")
                return new_url
        return url

    async def _run_bash_script(self,
                                target_url: str,
                                objective: str,
                                allowed_tools: Optional[list],
                                context: str) -> tuple[str, str]:
        tools_str   = ", ".join(allowed_tools) if allowed_tools else "curl, nikto"
        context_str = f"Context from previous steps:\n{context}" if context else ""

        script_prompt = (
            _load("recon_script_prompt.txt")
            .replace("__TARGET_URL__",    target_url)
            .replace("__OBJECTIVE__",     objective)
            .replace("__ALLOWED_TOOLS__", tools_str)
            .replace("__CONTEXT__",       context_str)
        )
        script_text = self.llm._call(script_prompt, phase="recon_plan")
        script = _extract_script(script_text)

        if not script:
            return "(no script)", "ERROR: LLM produced no script"

        # Safety: | head closes pipe early → SIGPIPE kills tool before results appear.
        script = re.sub(r"\|\s*head\b[^\n]*", "| cat", script)

        # Safety: grep -P / grep -oP silently produces empty output on Kali.
        if re.search(r'\bgrep\s+["\']?-[a-zA-Z]*P', script):
            print("[ReconAgent] grep -P/-oP detected — asking LLM to rewrite with POSIX grep...")
            fix_prompt = (
                "The bash script below uses 'grep -P' or 'grep -oP' (Perl regex) which silently "
                "fails on Kali Linux — it produces empty output with exit code 0.\n"
                "Replace ALL grep -P and grep -oP patterns with POSIX-compatible grep -o.\n"
                "Output ONLY the corrected bash script, no explanation.\n\n"
                f"Script:\n{script}"
            )
            fixed = self.llm._call(fix_prompt, phase="recon_fix")
            script = _extract_script(fixed) or script
            print("[ReconAgent] grep -P fix applied")

        print(f"[ReconAgent] Script:\n{script[:400]}")

        MAX_FIX_ATTEMPTS = 2
        raw_output = ""
        for attempt in range(MAX_FIX_ATTEMPTS + 1):
            try:
                raw_output = await self.kali.execute(script)
            except BaseException as e:
                return script, f"ERROR: Kali execution failed: {e}"

            exit_code = _extract_exit_code(raw_output)
            print(f"[ReconAgent] Attempt {attempt+1} — exit code: {exit_code}")

            if exit_code == 0 or exit_code is None or attempt == MAX_FIX_ATTEMPTS:
                break

            print(f"[ReconAgent] Script failed (exit {exit_code}), asking LLM to fix...")
            fix_prompt = (
                f"The bash script below failed with exit code {exit_code}.\n\n"
                f"Script:\n```bash\n{script}\n```\n\n"
                f"Error output:\n{raw_output[:1000]}\n\n"
                f"Fix the syntax or command error. Output ONLY the corrected bash script, no explanation."
            )
            fixed = self.llm._call(fix_prompt, phase="recon_fix")
            script = _extract_script(fixed) or script

        return script, raw_output

    def _parse_structured(self, tool: str, raw_output: str) -> ReconResult:
        """Code-based parsing for tools with structured output — no LLM call."""
        PARSERS = {
            "nmap":       parse_nmap,
            "gobuster":   parse_gobuster,
            "zap-spider": parse_zap_spider,
            "zap-active": parse_zap_alerts,
            "autorecon":  parse_autorecon,
        }
        parser = PARSERS.get(tool)
        findings = parser(raw_output) if parser else []

        if not findings:
            return ReconResult(
                raw_summary=f"{tool} completed but found no results",
                raw_output=raw_output,
            )
        return ReconResult(
            findings=findings,
            raw_summary=f"{tool}: {len(findings)} findings extracted",
        )

    def _parse(self, raw_text: str) -> ReconResult:
        try:
            data = json.loads(raw_text)
        except Exception as e:
            return ReconResult(raw_summary=raw_text[:200], error=f"JSON parse failed: {e}")

        if not isinstance(data, dict) or "findings" not in data:
            return ReconResult(raw_summary=raw_text[:200], error="Missing 'findings' key in response")

        findings = [
            {
                "type":       f.get("type", "unknown"),
                "value":      f.get("value", ""),
                "confidence": f.get("confidence", "medium"),
                "evidence":   f.get("evidence", ""),
            }
            for f in data.get("findings", [])
            if isinstance(f, dict) and f.get("type") and f.get("value")
        ]

        return ReconResult(
            findings=findings,
            dead_ends=data.get("dead_ends", []),
            raw_summary=data.get("raw_summary", ""),
        )
