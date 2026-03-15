from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


def _now() -> str:
    return datetime.now().isoformat()

def _id() -> str:
    return str(uuid.uuid4())[:8]


@dataclass
class Finding:
    id:          str
    session_id:  int
    type:        str    # directory, service, credential, vulnerability, rce, auth, parameter
    value:       str
    confidence:  str    # low, medium, high
    evidence:    str    # what proves this

    task_id:     Optional[str] = None
    is_verified: bool = False   # True = Execute Agent confirmed it

    created_at:  str = field(default_factory=_now)
    db_id:       Optional[int] = None


@dataclass
class Hypothesis:
    id:          str
    session_id:  int
    description: str
    confidence:  float  # 0.0 to 1.0

    status:     str  = 'active'   # active, confirmed, rejected
    supporting: list = field(default_factory=list)  # Finding ids

    created_at: str = field(default_factory=_now)
    db_id:      Optional[int] = None


@dataclass
class Task:
    id:          str
    session_id:  int
    description: str
    status:      str = 'pending'  # pending, in_progress, completed, failed
    label:       str = ""   # human-readable: "1", "1.2", "1.2.3"
    note:        str = ""   # brief outcome written by LLM when completing/failing

    task_type:  str = 'discover'  # discover | exploit | verify
    parent_id:  Optional[str] = None
    children:   list = field(default_factory=list)  # task ids

    source_finding_id: Optional[str] = None  # which finding spawned this task

    evidence_required: str               = ""
    evidence_found:    Optional[Finding] = None

    attempt_count: int = 0
    max_attempts:  int = 3

    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    db_id:      Optional[int] = None

    @property
    def can_retry(self) -> bool:
        return self.attempt_count < self.max_attempts and self.status != 'completed'


@dataclass
class PentestState:
    session_id:  int
    target_url:  str
    target_name: str
    goal:        str   # shell, root, auth_bypass, data_exfil
    scope:       str   # scope gate rejects actions outside this

    target_os: Optional[str] = None  # discovered by Recon, not always known upfront

    tasks:           dict = field(default_factory=dict)  # task_id -> Task (DB logging only)
    tasks_by_label:  dict = field(default_factory=dict)   # label -> task_id
    root_task_id:    Optional[str] = None
    current_task_id: Optional[str] = None

    findings:          list = field(default_factory=list)   # List[Finding]
    hypotheses:        list = field(default_factory=list)   # List[Hypothesis], sorted by confidence
    failed_approaches: list = field(default_factory=list)   # strings, redundancy gate checks this
    action_history:    list = field(default_factory=list)   # agent types with result summaries

    total_cost_usd: float = 0.0
    total_turns:    int   = 0
    max_cost_usd:   float = 5.0
    max_turns:      int   = 50

    goal_achieved: bool          = False
    goal_evidence: Optional[str] = None

    db: object = field(default=None, repr=False, compare=False)

    def create_task(self, description: str, evidence_required: str = "",
                    parent_id: Optional[str] = None, max_attempts: int = 3,
                    task_type: str = "discover",
                    source_finding_id: Optional[str] = None) -> Task:
        task = Task(
            id=f"task_{_id()}",
            session_id=self.session_id,
            description=description,
            evidence_required=evidence_required,
            parent_id=parent_id,
            max_attempts=max_attempts,
            task_type=task_type,
            source_finding_id=source_finding_id,
        )
        self.tasks[task.id] = task

        if parent_id and parent_id in self.tasks:
            self.tasks[parent_id].children.append(task.id)

        if self.root_task_id is None:
            self.root_task_id = task.id

        if self.db:
            parent_db_id = self.tasks[parent_id].db_id if parent_id and parent_id in self.tasks else None
            task.db_id = self.db.log_task(task, parent_db_id=parent_db_id)

        return task

    def update_task_status(self, task_id: str, status: str,
                           evidence: Optional[Finding] = None) -> None:
        task = self.tasks[task_id]

        task.status = status
        task.updated_at = _now()

        if status == 'failed':
            task.attempt_count += 1

        if evidence is not None:
            task.evidence_found = evidence

        if self.db and task.db_id:
            self.db.update_task(
                task_id=task.db_id,
                status=status,
                attempt_count=task.attempt_count,
                evidence_found=(evidence.__dict__ if evidence else None),
                updated_at=task.updated_at,
            )

    def set_current_task(self, task_id: str) -> None:
        if task_id not in self.tasks:
            raise KeyError(f"Task '{task_id}' not found")
        self.current_task_id = task_id
        self.update_task_status(task_id, 'in_progress')

    def get_pending_tasks(self) -> list:
        return [t for t in self.tasks.values() if t.status == 'pending']

    def get_retryable_tasks(self) -> list:
        """Failed tasks that haven't hit max_attempts yet."""
        return [t for t in self.tasks.values() if t.status == 'failed' and t.can_retry]

    def finding_has_task(self, finding_id: str) -> bool:
        """Return True if an exploit/verify task already exists for this finding."""
        return any(t.source_finding_id == finding_id for t in self.tasks.values())

    def add_finding(self, type: str, value: str, confidence: str, evidence: str,
                    task_id: Optional[str] = None, verified: bool = False) -> Finding:
        f = Finding(
            id=f"find_{_id()}",
            session_id=self.session_id,
            type=type,
            value=value,
            confidence=confidence,
            evidence=evidence,
            task_id=task_id,
            is_verified=verified,
        )
        self.findings.append(f)

        if self.db:
            f.db_id = self.db.log_finding(f)

        return f

    def add_hypothesis(self, description: str, confidence: float) -> Hypothesis:
        h = Hypothesis(
            id=f"hyp_{_id()}",
            session_id=self.session_id,
            description=description,
            confidence=max(0.0, min(1.0, confidence)),
        )
        self.hypotheses.append(h)
        self.hypotheses.sort(key=lambda x: x.confidence, reverse=True)

        if self.db:
            h.db_id = self.db.log_hypothesis(h)

        return h

    def update_hypothesis(self, hypothesis_id: str, confidence: Optional[float] = None,
                          status: Optional[str] = None) -> None:
        for h in self.hypotheses:
            if h.id == hypothesis_id:
                if confidence is not None:
                    h.confidence = max(0.0, min(1.0, confidence))
                if status is not None:
                    h.status = status
                self.hypotheses.sort(key=lambda x: x.confidence, reverse=True)
                return
        raise KeyError(f"Hypothesis '{hypothesis_id}' not found")

    def record_action(self, entry: str) -> None:
        self.action_history.append(entry)

    def add_failed_approach(self, approach: str) -> None:
        if approach not in self.failed_approaches:
            self.failed_approaches.append(approach)
            if self.db:
                self.db.log_raw("state", "INFO",
                                f"Dead end: {approach}",
                                {"session_id": self.session_id})

    def task_tree_snapshot(self) -> str:
        """Render the labeled task tree for the coordinator LLM prompt."""
        if not self.root_task_id:
            return "(no tasks yet)"

        STATUS_ICON = {
            "pending":     "[ ]",
            "in_progress": "[→]",
            "completed":   "[✓]",
            "failed":      "[✗]",
        }

        lines = []

        def _render(task_id: str, depth: int) -> None:
            task = self.tasks.get(task_id)
            if not task:
                return
            indent  = "    " * depth
            icon    = STATUS_ICON.get(task.status, "[?]")
            label   = f"{task.label} " if task.label else ""
            note    = f" — {task.note}" if task.note else ""
            lines.append(f"{indent}{icon} {label}{task.description}{note}")
            for child_id in task.children:
                _render(child_id, depth + 1)

        _render(self.root_task_id, 0)
        return "\n".join(lines)

    def create_labeled_task(self, parent_label: Optional[str], description: str,
                             status: str = "pending", task_type: str = "discover") -> "Task":
        """Create a task with an auto-assigned human-readable label."""
        if parent_label is None:
            label     = "1"
            parent_id = None
        else:
            parent_task = self.get_task_by_label(parent_label)
            if not parent_task:
                raise KeyError(f"Parent label '{parent_label}' not found in tree")
            n_children = len(parent_task.children)
            label      = f"{parent_label}.{n_children + 1}"
            parent_id  = parent_task.id

        task = self.create_task(
            description=description,
            parent_id=parent_id,
            task_type=task_type,
        )
        task.label  = label
        task.status = status
        self.tasks_by_label[label] = task.id
        return task

    def get_task_by_label(self, label: str) -> Optional["Task"]:
        """Look up a task by its human-readable label."""
        task_id = self.tasks_by_label.get(label)
        return self.tasks.get(task_id) if task_id else None

    def set_task_note(self, label: str, note: str) -> None:
        """Set the outcome note on a task (called by coordinator after agent result)."""
        task = self.get_task_by_label(label)
        if task:
            task.note = note[:120]

    def get_findings_by_type(self, type: str) -> list:
        return [f for f in self.findings if f.type == type]

    def consume(self, cost_usd: float = 0.0) -> None:
        self.total_cost_usd += cost_usd
        self.total_turns += 1

        if self.db:
            self.db.update_run_budget(self.session_id, self.total_cost_usd, self.total_turns)

    def within_budget(self) -> bool:
        return self.total_cost_usd < self.max_cost_usd and self.total_turns < self.max_turns

    def stop_reason(self) -> Optional[str]:
        if self.goal_achieved:
            return "goal_achieved"
        if self.total_cost_usd >= self.max_cost_usd:
            return "budget_cost_exceeded"
        if self.total_turns >= self.max_turns:
            return "budget_turns_exceeded"
        active = [t for t in self.tasks.values()
                  if t.status not in ("completed", "failed")]
        if not active:
            return "no_remaining_tasks"
        return None

    def mark_goal_achieved(self, evidence: str) -> None:
        self.goal_achieved = True
        self.goal_evidence = evidence

        if self.db:
            self.db.update_run_final_evidence(self.session_id, evidence)

    def _prioritized_findings(self, n: int = 20) -> list:
        """
        Return up to n findings prioritised by importance.
        Critical types (vulnerability, auth, credential, rce, authenticated)
        are always included first; remaining slots go to the most recent others.
        """
        CRITICAL = {"vulnerability", "auth", "credential", "rce", "authenticated"}
        critical = [f for f in self.findings if f.type in CRITICAL]
        rest     = [f for f in self.findings if f.type not in CRITICAL]
        # most-recent rest fills remaining slots
        combined = critical + rest[-(n - len(critical)):] if len(critical) < n else critical
        return combined[:n]

    def to_brain_snapshot(self) -> dict:
        """Compact view for the Brain's LLM prompt — not the full state."""
        return {
            "target_url":    self.target_url,
            "target_os":     self.target_os,
            "goal":          self.goal,
            "goal_achieved": self.goal_achieved,

            "pentest_task_tree": self.task_tree_snapshot(),

            "recent_findings": [
                {"type": f.type, "value": f.value,
                 "confidence": f.confidence, "evidence": f.evidence,
                 "verified": f.is_verified}
                for f in self._prioritized_findings()
            ],

            "top_hypotheses": [
                {"description": h.description,
                 "confidence": h.confidence, "status": h.status}
                for h in self.hypotheses
                if h.status != "rejected"
            ][:5],

            "failed_approaches": self.failed_approaches,

            # Full action history with summaries — the brain's episodic memory
            "action_history": self.action_history[-10:],

            "budget_remaining": {
                "cost_usd": round(self.max_cost_usd - self.total_cost_usd, 4),
                "turns":    self.max_turns - self.total_turns,
            },
        }

    def summary(self) -> str:
        completed = sum(1 for t in self.tasks.values() if t.status == 'completed')
        return (
            f"[{self.target_name}] goal={'DONE' if self.goal_achieved else self.goal} | "
            f"tasks={completed}/{len(self.tasks)} | findings={len(self.findings)} | "
            f"turns={self.total_turns} | cost=${self.total_cost_usd:.4f}"
        )
