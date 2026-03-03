from __future__ import annotations

import argparse
import asyncio
import json
import re
import traceback
from pathlib import Path
from typing import Optional

from agents.config.settings import llm_settings
from agents.helpers.run_logger import RunLogger
from agents.helpers.vault_rag import VaultRAG
from agents.llms.OpenRouter import OpenRouterLLM
from agents.logger import DatabaseLogger
from agents.recon_agent import ReconAgent, ReconResult
from agents.execute_agent import ExecuteAgent, ExecuteResult
from agents.state import PentestState


def _load_prompt() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "coordinator_prompt.txt"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class Coordinator:
    def __init__(self, llm, state: PentestState):
        self.llm     = llm
        self.state   = state
        self.recon   = ReconAgent(llm)
        self.execute = ExecuteAgent(llm)
        self.vault   = VaultRAG()
        self._prompt = _load_prompt()
        self.logger  = RunLogger(
            target_name=state.target_name,
            target_url=state.target_url,
            goal=state.goal,
            scope=state.scope,
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> PentestState:
        root = self.state.create_task(
            description=f"Pentest {self.state.target_url} — goal: {self.state.goal}",
            evidence_required="goal achieved or all reasonable paths exhausted",
        )
        self.state.set_current_task(root.id)

        last_result = "No actions taken yet."

        while not self.state.stop_reason():
            turn = self.state.total_turns + 1
            print(f"\n{'='*60}")
            print(f"[Coordinator] Turn {turn}")

            # 1. Vault RAG — query based on best hypothesis or goal
            topic       = self._vault_topic()
            rag_context = await self.vault.query(topic) if topic else ""

            # 2. Build prompt
            snapshot_dict = self.state.to_brain_snapshot()
            snapshot      = json.dumps(snapshot_dict, indent=2)
            prompt = (
                self._prompt
                .replace("__TARGET_URL__",     self.state.target_url)
                .replace("__GOAL__",           self.state.goal)
                .replace("__SCOPE__",          self.state.scope)
                .replace("__RAG_CONTEXT__",    rag_context)
                .replace("__STATE_SNAPSHOT__", snapshot)
                .replace("__LAST_RESULT__",    last_result)
            )

            # 3. Call LLM directly — coordinator does not use tools
            response  = self.llm._call(prompt, phase="coordinator")
            reasoning = self._extract_reasoning(response)
            print(f"[Coordinator] Reasoning:\n{reasoning}")

            # 4. Parse ACTION block
            action = self._parse_action(response)
            if action is None:
                print("[Coordinator] Could not parse ACTION block — stopping")
                break

            agent = action.get("agent", "")
            print(f"[Coordinator] → {agent.upper()}: {action.get('task') or action.get('reason', '')}")

            # 5. Dispatch
            agent_result      = None
            agent_result_text = ""
            findings_before   = len(self.state.findings)
            hypotheses_before = len(self.state.hypotheses)
            failed_before     = len(self.state.failed_approaches)

            if agent == "recon":
                result            = await self.recon.run(
                    target_url=self.state.target_url,
                    objective=action["task"],
                )
                last_result       = self._format_recon(result)
                agent_result_text = last_result
                self._ingest_recon(result)
                agent_result = {
                    "findings":   result.findings,
                    "hypotheses": result.hypotheses,
                    "dead_ends":  result.dead_ends,
                    "raw_summary": result.raw_summary,
                    "error":      result.error,
                }

            elif agent == "execute":
                result            = await self.execute.run(
                    target_url=self.state.target_url,
                    task=action["task"],
                    allowed_tools=action.get("allowed_tools"),
                    context=self._context_for_execute(),
                )
                last_result       = self._format_execute(result)
                agent_result_text = last_result
                self._ingest_execute(result)
                agent_result = {
                    "success":        result.success,
                    "output_summary": result.output_summary,
                    "key_facts":      result.key_facts,
                    "raw_output":     result.raw_output,
                    "error":          result.error,
                }

            elif agent == "done":
                if action.get("success"):
                    self.state.mark_goal_achieved(evidence=action.get("evidence", ""))
                    print(f"[Coordinator] GOAL ACHIEVED: {action.get('evidence', '')}")
                else:
                    print(f"[Coordinator] Giving up: {action.get('reason', '')}")

                self.logger.log_turn(
                    turn=turn, vault_context=rag_context,
                    state_snapshot=snapshot_dict, prompt=prompt,
                    llm_response=response, reasoning=reasoning,
                    action=action, agent_type="done",
                    agent_result=None, agent_result_text="",
                    findings_added=[], hypotheses_added=[], failed_added=[],
                )
                break

            else:
                print(f"[Coordinator] Unknown agent '{agent}' — stopping")
                break

            # 6. Log turn
            self.logger.log_turn(
                turn=turn,
                vault_context=rag_context,
                state_snapshot=snapshot_dict,
                prompt=prompt,
                llm_response=response,
                reasoning=reasoning,
                action=action,
                agent_type=agent,
                agent_result=agent_result,
                agent_result_text=agent_result_text,
                findings_added=[
                    {"type": f.type, "value": f.value, "confidence": f.confidence, "evidence": f.evidence}
                    for f in self.state.findings[findings_before:]
                ],
                hypotheses_added=[
                    {"description": h.description, "confidence": h.confidence}
                    for h in self.state.hypotheses[hypotheses_before:]
                ],
                failed_added=self.state.failed_approaches[failed_before:],
            )

            # 7. Consume one turn
            self.state.consume()

        reason = self.state.stop_reason()
        print(f"\n{'='*60}")
        print(f"[Coordinator] Run ended — {reason}")
        print(self.state.summary())

        self.logger.finalize(
            stop_reason=reason or "unknown",
            final_state={
                "goal_achieved":  self.state.goal_achieved,
                "goal_evidence":  self.state.goal_evidence,
                "total_turns":    self.state.total_turns,
                "total_cost_usd": self.state.total_cost_usd,
                "findings": [
                    {"type": f.type, "value": f.value,
                     "confidence": f.confidence, "evidence": f.evidence}
                    for f in self.state.findings
                ],
                "hypotheses": [
                    {"description": h.description, "confidence": h.confidence,
                     "status": h.status}
                    for h in self.state.hypotheses
                ],
            }
        )

        return self.state

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_action(self, text: str) -> Optional[dict]:
        match = re.search(r"ACTION:\s*(\{.*\})", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except Exception as e:
            print(f"[Coordinator] JSON parse error: {e}")
            return None

    def _extract_reasoning(self, text: str) -> str:
        parts = re.split(r"ACTION:", text, maxsplit=1)
        return parts[0].strip()[:600] if parts else ""

    def _vault_topic(self) -> str:
        if self.state.hypotheses:
            return self.state.hypotheses[0].description
        if self.state.findings:
            return self.state.findings[-1].value
        return self.state.goal

    def _context_for_execute(self) -> str:
        lines = []
        for f in self.state.findings[-5:]:
            lines.append(f"{f.type}: {f.value} ({f.confidence}) — {f.evidence}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Ingest agent results into state
    # ------------------------------------------------------------------

    def _ingest_recon(self, result: ReconResult) -> None:
        for f in result.findings:
            self.state.add_finding(
                type=f.get("type", "unknown"),
                value=f.get("value", ""),
                confidence=f.get("confidence", "medium"),
                evidence=f.get("evidence", ""),
            )
        for h in result.hypotheses:
            self.state.add_hypothesis(
                description=h.get("description", ""),
                confidence=float(h.get("confidence", 0.5)),
            )
        for d in result.dead_ends:
            self.state.add_failed_approach(d)

    def _ingest_execute(self, result: ExecuteResult) -> None:
        for kf in result.key_facts:
            fact  = kf.get("fact", "")
            ftype = "credential" if any(
                w in fact.lower() for w in ("password", "session", "cookie", "token")
            ) else "parameter"
            self.state.add_finding(
                type=ftype,
                value=fact,
                confidence="high",
                evidence=result.output_summary,
                verified=True,
            )
        if not result.success and result.output_summary:
            self.state.add_failed_approach(result.output_summary[:200])

    # ------------------------------------------------------------------
    # Format results for __LAST_RESULT__ in next prompt
    # ------------------------------------------------------------------

    def _format_recon(self, result: ReconResult) -> str:
        lines = ["[Recon Agent Result]", f"Summary: {result.raw_summary}"]
        for f in result.findings:
            lines.append(f"  FINDING [{f['confidence']}] {f['type']}: {f['value']}")
        for h in result.hypotheses:
            lines.append(f"  HYPOTHESIS [{h['confidence']:.0%}]: {h['description']}")
        for d in result.dead_ends:
            lines.append(f"  DEAD END: {d}")
        return "\n".join(lines)

    def _format_execute(self, result: ExecuteResult) -> str:
        lines = [f"[Execute Agent Result] success={result.success}"]
        lines.append(f"Summary: {result.output_summary}")
        for kf in result.key_facts:
            lines.append(f"  FACT: {kf['fact']} — {kf.get('significance', '')}")
        if result.error:
            lines.append(f"  ERROR: {result.error}")
        return "\n".join(lines)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="PLANTE v2 Coordinator")
    parser.add_argument("--target-url",  required=True)
    parser.add_argument("--goal",        default="auth_bypass",
                        choices=["auth_bypass", "shell", "data_exfil"])
    parser.add_argument("--scope",       default=None,
                        help="Scope IP/domain. Defaults to target host.")
    parser.add_argument("--target-name", default="target")
    parser.add_argument("--max-turns",   type=int,   default=20)
    parser.add_argument("--max-cost",    type=float, default=5.0)
    args = parser.parse_args()

    from urllib.parse import urlparse
    scope = args.scope or urlparse(args.target_url).hostname

    llm = OpenRouterLLM()

    try:
        db         = DatabaseLogger()
        session_id = db.log_run_start(
            target=args.target_url,
            tester=llm_settings.TESTER_NAME,
            model=llm.model_name,
        )
    except Exception:
        print("[Coordinator] DB unavailable — running without logging")
        db         = None
        session_id = 1

    state = PentestState(
        session_id=session_id,
        target_url=args.target_url,
        target_name=args.target_name,
        goal=args.goal,
        scope=scope,
        max_turns=args.max_turns,
        max_cost_usd=args.max_cost,
        db=db,
    )

    coordinator = Coordinator(llm, state)
    await coordinator.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except* Exception as eg:
        for exc in eg.exceptions:
            traceback.print_exception(type(exc), exc, exc.__traceback__)
