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
from agents.helpers.payloads_rag import PayloadsRAG
from agents.llms.OpenRouter import OpenRouterLLM
from agents.config.constants import WORKER_MODEL_NAME
from agents.logger import DatabaseLogger
from agents.recon_agent import ReconAgent, ReconResult
from agents.execute_agent import ExecuteAgent, ExecuteResult
from agents.state import PentestState
from agents.helpers.token_tracker import token_tracker


def _load_prompt() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "coordinator_prompt.txt"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class Coordinator:
    def __init__(self, llm, state: PentestState, worker_llm=None):
        self.llm     = llm
        self.state   = state
        _worker      = worker_llm or llm
        self.recon   = ReconAgent(_worker)
        self.execute = ExecuteAgent(_worker)
        self.vault   = PayloadsRAG()
        self._prompt = _load_prompt()
        self.logger   = RunLogger(
            target_name=state.target_name,
            target_url=state.target_url,
            goal=state.goal,
            scope=state.scope,
        )
        self._rag_query = ""  # set by LLM after first recon; empty = skip RAG on Turn 1

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> PentestState:
        # Build the initial labeled task tree
        self.state.create_labeled_task(None,
            f"Compromise {self.state.target_url} — goal: {self.state.goal}",
            status="in_progress")
        self.state.create_labeled_task("1", "Discover — map services, endpoints, and attack surface")
        self.state.create_labeled_task("1", "Authenticate — gain valid session or credentials")
        self.state.create_labeled_task("1", "Exploit — use access for RCE or file execution")
        self.state.create_labeled_task("1", "Escalate — read flags or achieve full access")

        last_result = "No actions taken yet."
        _run_error  = None

        while True:
          # Open both KaliMCP subprocesses — reopened on each extension iteration.
          # Use async with so anyio cancel scopes are always closed in the same task.
          async with self.recon.kali, self.execute.kali:
            try:
              while not self.state.stop_reason():
                turn = self.state.total_turns + 1
                print(f"\n{'='*60}")
                print(f"[Coordinator] Turn {turn}")

                # 1. Print task tree + state summary
                print(f"\n[Task Tree]\n{self.state.task_tree_snapshot()}")
                print(f"[State] findings={len(self.state.findings)} | failed={len(self.state.failed_approaches)}")
                if self.state.action_history:
                    print(f"[History] {self.state.action_history[-1]}")

                # 2. Vault RAG — topic set by coordinator last turn via rag_query field
                topic       = self._rag_query
                rag_context = await self.vault.query(topic) if topic else ""
                print(f"[RAG] topic: '{topic[:80]}'")
                if rag_context:
                    categories = [line.lstrip('[').split(']')[0] for line in rag_context.splitlines() if line.startswith('[')]
                    print(f"[RAG] returned: {categories}")
                else:
                    print(f"[RAG] no results")

                # 3. Build prompt
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
                response  = self.llm._call(prompt, phase="coordinator", json_mode=True)
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
                failed_before     = len(self.state.failed_approaches)
    
                if agent == "recon":
                    result            = await self.recon.run(
                        target_url=self.state.target_url,
                        objective=action["task"],
                        allowed_tools=action.get("allowed_tools"),
                    )
                    last_result       = self._format_recon(result)
                    agent_result_text = last_result
                    print(f"\n{last_result}")
                    await self._ingest_recon(result)
                    # Mark current discover task done (but never the root task),
                    # then point back to root so LLM always sees active work.
                    cur_id = self.state.current_task_id
                    if cur_id and cur_id != self.state.root_task_id:
                        ct = self.state.tasks[cur_id]
                        if ct.task_type == 'discover' and ct.status == 'in_progress':
                            self.state.update_task_status(cur_id, 'completed')
                    self.state.current_task_id = self.state.root_task_id
                    agent_result = {
                        "findings":   result.findings,
                        "dead_ends":  result.dead_ends,
                        "raw_summary": result.raw_summary,
                        "error":      result.error,
                        "script":     result.script,
                        "raw_output": result.raw_output,
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
                    print(f"\n{last_result}")
                    self._ingest_execute(result)
                    # Update exploit/verify task status based on result
                    if self.state.current_task_id:
                        ct = self.state.tasks[self.state.current_task_id]
                        if ct.task_type in ('exploit', 'verify') and ct.status == 'in_progress':
                            new_status = 'completed' if result.success else 'failed'
                            self.state.update_task_status(self.state.current_task_id, new_status)
                            print(f"[Coordinator] Task {new_status}: {ct.description[:60]}")
                    agent_result = {
                        "success":        result.success,
                        "output_summary": result.output_summary,
                        "raw_output":     result.raw_output,
                        "error":          result.error,
                        "script":         result.script,
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
                        findings_added=[], failed_added=[],
                    )
                    break
    
                else:
                    print(f"[Coordinator] Unknown agent '{agent}' — stopping")
                    break
    
                # 6. Apply tree operations from coordinator
                current_label = action.get("current_task", "")

                # Mark current task in_progress
                if current_label:
                    cur = self.state.get_task_by_label(current_label)
                    if cur and cur.status == "pending":
                        self.state.update_task_status(cur.id, "in_progress")

                # Complete tasks LLM marked done
                for t in action.get("complete_tasks", []):
                    lbl  = t.get("label", "")
                    note = t.get("note", "")
                    task = self.state.get_task_by_label(lbl)
                    if task:
                        self.state.set_task_note(lbl, note)
                        self.state.update_task_status(task.id, "completed")
                        print(f"[Tree] ✓ completed {lbl} — {note[:60]}")

                # Fail tasks LLM marked failed
                for t in action.get("fail_tasks", []):
                    lbl  = t.get("label", "")
                    note = t.get("note", "")
                    task = self.state.get_task_by_label(lbl)
                    if task:
                        self.state.set_task_note(lbl, note)
                        self.state.update_task_status(task.id, "failed")
                        self.state.add_failed_approach(f"{task.description}: {note}"[:200])
                        print(f"[Tree] ✗ failed   {lbl} — {note[:60]}")

                # Add new child tasks
                for t in action.get("add_tasks", []):
                    parent = t.get("parent", "").strip()
                    desc   = t.get("description", "").strip()
                    if parent and desc:
                        try:
                            new_task = self.state.create_labeled_task(parent, desc)
                            print(f"[Tree] + added    {new_task.label} under {parent} — {desc[:60]}")
                        except KeyError as e:
                            print(f"[Tree] ! bad parent '{parent}': {e}")

                # Update RAG query for next turn
                if action.get("rag_query"):
                    self._rag_query = action["rag_query"]
                    print(f"[RAG] next query: '{self._rag_query}'")

                print(f"\n[Task Tree Updated]\n{self.state.task_tree_snapshot()}")

                # 7. Record action with result summary for episodic memory
                tools      = action.get("allowed_tools", [])
                tool_str   = f" ({', '.join(tools)})" if tools else ""
                summary    = (getattr(agent_result, "raw_summary", None)
                              or getattr(agent_result, "output_summary", None)
                              or (agent_result.get("raw_summary") or agent_result.get("output_summary", "")
                                  if isinstance(agent_result, dict) else ""))
                success    = (agent_result.get("success") if isinstance(agent_result, dict) else None)
                tag        = " [OK]" if success is True else " [FAILED]" if success is False else ""
                entry      = f"Turn {turn} {agent}{tool_str}: {str(summary)[:120]}{tag}" if summary else f"Turn {turn} {agent}{tool_str}{tag}"
                self.state.record_action(entry)
    
                # 8. Log turn
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
                    failed_added=self.state.failed_approaches[failed_before:],
                )
    
                # 9. Consume one turn (use actual OpenRouter cost if available)
                cost_before = getattr(self, "_last_cost", 0.0)
                cost_now    = token_tracker.total_actual_cost()
                turn_cost   = max(0.0, cost_now - cost_before)
                self._last_cost = cost_now
                self.state.consume(cost_usd=turn_cost)
                print(f"[Coordinator] Turn cost: ${turn_cost:.4f} | Total: ${self.state.total_cost_usd:.4f}")
    
            except Exception as e:
              _run_error = str(e)
              print(f"[Coordinator] CRASHED: {e}")

          # Extension prompt — ask user to add more turns if budget exhausted
          if (self.state.stop_reason() == "budget_turns_exceeded"
                  and not self.state.goal_achieved
                  and not _run_error):
              try:
                  raw   = input(f"\n[+] {self.state.total_turns} turns used. Add how many more? (0 to stop): ").strip()
                  extra = int(raw) if raw else 0
              except (ValueError, EOFError):
                  extra = 0
              if extra > 0:
                  self.state.max_turns += extra
                  print(f"[Coordinator] +{extra} turns — {self.state.max_turns - self.state.total_turns} remaining")
                  continue
          break

        reason = self.state.stop_reason() or (_run_error and f"error: {_run_error}") or "unknown"
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
            }
        )

        return self.state

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_action(self, text: str) -> Optional[dict]:
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "agent" in data:
                return data
        except json.JSONDecodeError:
            pass
        print(f"[Coordinator] JSON parse failed — raw:\n{text[:300]}")
        return None

    def _extract_reasoning(self, text: str) -> str:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return str(data.get("reasoning", ""))[:600]
        except Exception:
            pass
        return text[:600]

    def _context_for_execute(self) -> str:
        lines = []
        for f in self.state.findings[-5:]:
            lines.append(f"{f.type}: {f.value} ({f.confidence}) — {f.evidence}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Ingest agent results into state
    # ------------------------------------------------------------------

    async def _verify_path(self, path: str) -> bool:
        """Returns False if path returns the same page as homepage (catch-all false positive)."""
        try:
            base = self.state.target_url.rstrip("/")
            script = (
                f'HOME=$(curl -s -L "{base}/" | grep -o "<title>[^<]*</title>" | head -1)\n'
                f'PATH_RESP=$(curl -s -L "{base}{path}" | grep -o "<title>[^<]*</title>" | head -1)\n'
                f'[ "$HOME" = "$PATH_RESP" ] && echo "CATCHALL" || echo "UNIQUE"'
            )
            out = await self.recon.kali.execute(script)
            return "UNIQUE" in out
        except Exception:
            return True  # on error, assume real — don't silently drop findings

    def _extract_path(self, value: str) -> Optional[str]:
        """Extract the first URL path (starts with /) from a finding value string."""
        m = re.search(r"(/[^\s\"'<>]+)", value)
        return m.group(1) if m else None

    async def _ingest_recon(self, result: ReconResult) -> None:
        catchall_paths: set = set()

        # Split findings into those needing path verification vs safe to add directly.
        # Only gobuster/autorecon "directory" findings need catch-all checks —
        # ZAP "vulnerability" findings are already confirmed by active probing.
        needs_verify: list = []
        direct:       list = []
        for f in result.findings:
            ftype = f.get("type", "unknown")
            value = f.get("value", "")
            path  = self._extract_path(value) if ftype == "directory" else None
            if path:
                needs_verify.append((ftype, value, path, f))
            else:
                direct.append(f)

        # Verify all directory paths in parallel — no sequential waiting
        if needs_verify:
            verify_results = await asyncio.gather(
                *[self._verify_path(path) for _, _, path, _ in needs_verify]
            )
            for (ftype, value, path, f), is_real in zip(needs_verify, verify_results):
                if not is_real:
                    print(f"[Coordinator] Filtered catch-all: {value}")
                    self.state.add_failed_approach(f"catch-all false positive: {path}")
                    catchall_paths.add(path)
                else:
                    self.state.add_finding(
                        type=ftype, value=value,
                        confidence=f.get("confidence", "medium"),
                        evidence=f.get("evidence", ""),
                    )

        for f in direct:
            self.state.add_finding(
                type=f.get("type", "unknown"),
                value=f.get("value", ""),
                confidence=f.get("confidence", "medium"),
                evidence=f.get("evidence", ""),
            )

        for d in result.dead_ends:
            self.state.add_failed_approach(d)

    def _ingest_execute(self, result: ExecuteResult) -> None:
        if result.success:
            # Signal that an authenticated session is now active —
            # coordinator will see raw output and decide next steps
            login_keywords = ("welcome", "logout", "logged in", "dashboard", "admin")
            if any(w in result.output_summary.lower() for w in login_keywords):
                self.state.add_finding(
                    type="authenticated",
                    value="Active session established — cookie saved to /tmp/plante_session.txt",
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
        for d in result.dead_ends:
            lines.append(f"  DEAD END: {d}")
        if result.raw_output:
            raw = result.raw_output
            truncated = len(raw) > 10000
            lines.append(f"\n[Raw Output]{' (truncated)' if truncated else ''}\n{raw[:10000]}")
        return "\n".join(lines)

    def _format_execute(self, result: ExecuteResult) -> str:
        lines = [f"[Execute Agent Result] success={result.success}"]
        lines.append(f"Summary: {result.output_summary}")
        if result.error:
            lines.append(f"  ERROR: {result.error}")
        if result.raw_output:
            raw = result.raw_output
            truncated = len(raw) > 10000
            lines.append(f"\n[Raw Output]{' (truncated)' if truncated else ''}\n{raw[:10000]}")
        return "\n".join(lines)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="PLANTE v2 Coordinator")
    parser.add_argument("--target-url",  required=True)
    parser.add_argument("--goal",        default="shell")
    parser.add_argument("--scope",       default=None,
                        help="Scope IP/domain. Defaults to target host.")
    parser.add_argument("--target-name", default="target")
    parser.add_argument("--max-turns",   type=int,   default=20)
    parser.add_argument("--max-cost",    type=float, default=5.0)
    args = parser.parse_args()

    from urllib.parse import urlparse
    scope = args.scope or urlparse(args.target_url).hostname

    llm        = OpenRouterLLM()                           # Grok-4 — coordinator only
    worker_llm = OpenRouterLLM(model_name=WORKER_MODEL_NAME)  # cheap — recon/execute
    print(f"[Coordinator] Models: coordinator={llm.model_name} | workers={worker_llm.model_name}")

    try:
        db         = DatabaseLogger()
        session_id = db.start_session(
            target_url=args.target_url,
            target_name=args.target_name,
            goal=args.goal,
            scope=scope,
            max_cost_usd=args.max_cost,
            max_turns=args.max_turns,
        )
        if not session_id:
            raise RuntimeError("start_session returned None")
    except Exception as e:
        print(f"[Coordinator] DB unavailable — running without logging ({e})")
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

    coordinator = Coordinator(llm, state, worker_llm=worker_llm)
    try:
        await coordinator.run()
    finally:
        if db:
            db.end_run(status="completed" if state.goal_achieved else "failed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except* Exception as eg:
        for exc in eg.exceptions:
            traceback.print_exception(type(exc), exc, exc.__traceback__)
