from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


RESULTS_V2 = Path(__file__).resolve().parents[2] / "results" / "v2"


class RunLogger:
    """
    Logs a full coordinator run to results/v2/<name>_<timestamp>/.

    Writes two files incrementally (one turn at a time so data is never
    lost if the run crashes):
      run.json  — structured log for debugging / machine parsing
      run.md    — human-readable chat history
    """

    def __init__(self, target_name: str, target_url: str, goal: str, scope: str):
        ts        = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.dir  = RESULTS_V2 / f"{target_name}_{ts}"
        self.dir.mkdir(parents=True, exist_ok=True)

        self.json_path = self.dir / "run.json"
        self.md_path   = self.dir / "run.md"

        self._turns: list = []
        self._meta = {
            "target_name": target_name,
            "target_url":  target_url,
            "goal":        goal,
            "scope":       scope,
            "started_at":  datetime.now().isoformat(),
            "ended_at":    None,
            "stop_reason": None,
            "turns":       self._turns,
            "final_state": None,
        }

        self._write_json()
        self._write_md_header(target_name, target_url, goal)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_turn(self,
                 turn:              int,
                 vault_context:     str,
                 state_snapshot:    dict,
                 prompt:            str,
                 llm_response:      str,
                 reasoning:         str,
                 action:            Optional[dict],
                 agent_type:        str,
                 agent_result:      Optional[dict],
                 agent_result_text: str,
                 findings_added:    list,
                 hypotheses_added:  list,
                 failed_added:      list) -> None:

        ts = datetime.now().isoformat()

        turn_data = {
            "turn":              turn,
            "timestamp":         ts,
            "vault_context":     vault_context,
            "state_snapshot":    state_snapshot,
            "prompt":            prompt,
            "llm_response":      llm_response,
            "reasoning":         reasoning,
            "action":            action,
            "agent_type":        agent_type,
            "agent_result":      agent_result,
            "agent_result_text": agent_result_text,
            "findings_added":    findings_added,
            "hypotheses_added":  hypotheses_added,
            "failed_added":      failed_added,
        }

        self._turns.append(turn_data)
        self._write_json()
        self._write_md_turn(turn_data)

    def finalize(self, stop_reason: str, final_state: dict) -> None:
        self._meta["ended_at"]    = datetime.now().isoformat()
        self._meta["stop_reason"] = stop_reason
        self._meta["final_state"] = final_state
        self._write_json()
        self._write_md_footer(stop_reason, final_state)
        print(f"[RunLogger] Saved to {self.dir}")

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def _write_json(self) -> None:
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(self._meta, f, indent=2, default=str)

    # ------------------------------------------------------------------
    # Markdown
    # ------------------------------------------------------------------

    def _write_md_header(self, name: str, url: str, goal: str) -> None:
        started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.md_path, "w", encoding="utf-8") as f:
            f.write(f"# PLANTE v2 Run — {name}\n\n")
            f.write(f"**Target**: {url}  \n")
            f.write(f"**Goal**: {goal}  \n")
            f.write(f"**Started**: {started}  \n\n")
            f.write("---\n")

    def _write_md_turn(self, d: dict) -> None:
        ts    = d["timestamp"].replace("T", " ")[:19]
        act   = d["action"] or {}
        agent = d["agent_type"].upper() if d["agent_type"] else "UNKNOWN"

        findings_lines  = "\n".join(
            f"- [{f.get('confidence','?').upper()}] {f.get('type','?')}: {f.get('value','?')}"
            for f in d["findings_added"]
        ) or "(none)"

        hypotheses_lines = "\n".join(
            f"- [{h.get('confidence', 0):.0%}] {h.get('description','?')}"
            for h in d["hypotheses_added"]
        ) or "(none)"

        failed_lines = "\n".join(f"- {a}" for a in d["failed_added"]) or "(none)"

        with open(self.md_path, "a", encoding="utf-8") as f:
            f.write(f"\n## Turn {d['turn']} — {ts}\n\n")

            # Vault context
            f.write("### Vault Context\n")
            f.write(f"```\n{d['vault_context'] or '(vault not running or no results)'}\n```\n\n")

            # State snapshot
            f.write("### State Snapshot\n")
            f.write(f"```json\n{json.dumps(d['state_snapshot'], indent=2)}\n```\n\n")

            # Full prompt
            f.write("### Coordinator Prompt\n")
            f.write(f"```\n{d['prompt']}\n```\n\n")

            # LLM response
            f.write("### LLM Response\n\n")
            f.write(f"**Reasoning:**\n{d['reasoning']}\n\n")
            f.write(f"**Action:**\n```json\n{json.dumps(act, indent=2)}\n```\n\n")

            # Agent result
            f.write(f"### {agent} Agent Result\n")
            f.write(f"```\n{d['agent_result_text'] or '(no result)'}\n```\n\n")

            # State changes
            f.write("### State Changes\n\n")
            f.write(f"**Findings added ({len(d['findings_added'])}):**\n{findings_lines}\n\n")
            f.write(f"**Hypotheses added ({len(d['hypotheses_added'])}):**\n{hypotheses_lines}\n\n")
            f.write(f"**Failed approaches added ({len(d['failed_added'])}):**\n{failed_lines}\n\n")

            f.write("---\n")

    def _write_md_footer(self, stop_reason: str, final_state: dict) -> None:
        goal_achieved = final_state.get("goal_achieved", False)
        status        = "GOAL ACHIEVED ✓" if goal_achieved else "NOT ACHIEVED ✗"
        evidence      = final_state.get("goal_evidence") or "—"
        turns         = final_state.get("total_turns", "?")
        cost          = final_state.get("total_cost_usd", 0)
        findings      = final_state.get("findings", [])
        hypotheses    = final_state.get("hypotheses", [])

        with open(self.md_path, "a", encoding="utf-8") as f:
            f.write(f"\n## Final Result\n\n")
            f.write(f"**Status**: {status}  \n")
            f.write(f"**Stop reason**: {stop_reason}  \n")
            f.write(f"**Evidence**: {evidence}  \n")
            f.write(f"**Turns**: {turns}  \n")
            f.write(f"**Cost**: ${cost:.4f}  \n\n")

            f.write("### All Findings\n")
            for finding in findings:
                f.write(f"- [{finding.get('confidence','?').upper()}] "
                        f"{finding.get('type','?')}: {finding.get('value','?')}  \n")
                if finding.get("evidence"):
                    f.write(f"  *{finding['evidence']}*  \n")

            f.write("\n### All Hypotheses\n")
            for h in hypotheses:
                f.write(f"- [{h.get('confidence',0):.0%}] [{h.get('status','?')}] "
                        f"{h.get('description','?')}  \n")
