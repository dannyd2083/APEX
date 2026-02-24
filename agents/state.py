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
    status:      str = 'pending'  # pending, in_progress, completed, stalled, failed

    parent_id: Optional[str] = None
    children:  list = field(default_factory=list)  # task ids

    # task cannot be marked completed without evidence_found set
    evidence_required: str               = ""
    evidence_found:    Optional[Finding] = None

    attempt_count: int = 0
    max_attempts:  int = 3
    assigned_to:   Optional[str] = None  # recon, execute

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

    tasks:           dict = field(default_factory=dict)  # task_id -> Task
    root_task_id:    Optional[str] = None
    current_task_id: Optional[str] = None

    findings:          list = field(default_factory=list)   # List[Finding]
    hypotheses:        list = field(default_factory=list)   # List[Hypothesis], sorted by confidence
    failed_approaches: list = field(default_factory=list)   # strings, redundancy gate checks this

    total_cost_usd: float = 0.0
    total_turns:    int   = 0
    max_cost_usd:   float = 5.0
    max_turns:      int   = 50

    goal_achieved: bool          = False
    goal_evidence: Optional[str] = None

    db: object = field(default=None, repr=False, compare=False)

    def create_task(self, description: str, evidence_required: str = "",
                    parent_id: Optional[str] = None, max_attempts: int = 3) -> Task:
        task = Task(
            id=f"task_{_id()}",
            session_id=self.session_id,
            description=description,
            evidence_required=evidence_required,
            parent_id=parent_id,
            max_attempts=max_attempts,
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

        if status == 'completed' and evidence is None:
            raise ValueError(f"Task '{task_id}' needs evidence to be marked completed")

        task.status = status
        task.updated_at = _now()

        if status in ('stalled', 'failed'):
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

    def get_stalled_tasks(self) -> list:
        return [t for t in self.tasks.values() if t.status == 'stalled' and t.can_retry]

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

    def add_failed_approach(self, approach: str) -> None:
        if approach not in self.failed_approaches:
            self.failed_approaches.append(approach)
            if self.db:
                self.db.log_raw("state", "INFO",
                                f"Dead end: {approach}",
                                {"session_id": self.session_id})

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
        if not self.get_pending_tasks() and not self.get_stalled_tasks():
            return "no_remaining_tasks"
        return None

    def mark_goal_achieved(self, evidence: str) -> None:
        self.goal_achieved = True
        self.goal_evidence = evidence

        if self.db:
            self.db.update_run_final_evidence(self.session_id, evidence)

    def to_brain_snapshot(self) -> dict:
        """Compact view for the Brain's LLM prompt — not the full state."""
        current = self.tasks.get(self.current_task_id) if self.current_task_id else None

        return {
            "target_url":    self.target_url,
            "target_os":     self.target_os,
            "goal":          self.goal,
            "goal_achieved": self.goal_achieved,

            "current_task": {
                "id":                current.id,
                "description":       current.description,
                "evidence_required": current.evidence_required,
                "attempt_count":     current.attempt_count,
                "max_attempts":      current.max_attempts,
            } if current else None,

            "pending_tasks": [
                {"id": t.id, "description": t.description}
                for t in self.get_pending_tasks()[:10]
            ],

            "recent_findings": [
                {"type": f.type, "value": f.value,
                 "confidence": f.confidence, "verified": f.is_verified}
                for f in self.findings[-10:]
            ],

            "top_hypotheses": [
                {"id": h.id, "description": h.description,
                 "confidence": h.confidence, "status": h.status}
                for h in self.hypotheses[:5]
            ],

            "failed_approaches": self.failed_approaches,

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
