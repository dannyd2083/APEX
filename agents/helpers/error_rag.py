from __future__ import annotations

import os
import re
from typing import Optional

try:
    import psycopg2
    import psycopg2.extras
    _PSYCOPG2_OK = True
except ImportError:
    _PSYCOPG2_OK = False

from rank_bm25 import BM25Okapi


def _tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"\W+", text.lower()) if len(t) > 1]


def _get_conn():
    """Open a psycopg2 connection from DB_* env vars. Returns None if unconfigured."""
    host     = os.getenv("DB_HOST")
    port     = os.getenv("DB_PORT", "5432")
    user     = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    dbname   = os.getenv("DB_NAME")
    if not all([host, user, password, dbname]):
        return None
    try:
        return psycopg2.connect(
            host=host, port=port, user=user, password=password,
            dbname=dbname, connect_timeout=5,
        )
    except Exception as e:
        print(f"[ErrorRAG] DB connection failed: {e}")
        return None


class ErrorRAG:
    def __init__(self, box_name: str):
        self.box_name = box_name
        self._written: set = set()   # (box_name, task) pairs written this run — dedup guard
        self._corpus:   Optional[list] = None
        self._metadata: Optional[list] = None
        self._bm25:     Optional[BM25Okapi] = None

    def write_failure(
        self,
        target_service: str,
        target_os: str,
        task: str,
        root_cause: str,
        lesson: str,
    ) -> None:
        """
        Persist a FUNDAMENTAL failure to error_paths.

        Skips silently if:
        - DB env vars not set (degraded mode)
        - Same box_name + task was already written this run (dedup)
        """
        dedup_key = (self.box_name, task[:200])
        if dedup_key in self._written:
            print(f"[ErrorRAG] Dedup skip: {task[:60]!r}")
            return

        if not _PSYCOPG2_OK:
            print("[ErrorRAG] psycopg2 not available — write skipped")
            return

        conn = _get_conn()
        if conn is None:
            print("[ErrorRAG] DB not configured (set DB_HOST/DB_USER/DB_PASSWORD/DB_NAME in .env) — write skipped")
            return

        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO error_paths
                            (box_name, target_service, target_os, task, root_cause, lesson)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            self.box_name,
                            target_service or "",
                            target_os or "",
                            task[:500],
                            root_cause[:1000],
                            lesson[:500],
                        ),
                    )
            self._written.add(dedup_key)
            # Invalidate BM25 cache so next query sees the new record
            self._corpus = self._metadata = self._bm25 = None
            print(f"[ErrorRAG] Wrote: box={self.box_name!r} task={task[:60]!r}")
        except Exception as e:
            print(f"[ErrorRAG] Write failed: {e}")
        finally:
            conn.close()

    def _build_index(self) -> bool:
        """Load all records from DB and build BM25 index. Returns False on failure."""
        if not _PSYCOPG2_OK:
            return False

        conn = _get_conn()
        if conn is None:
            return False

        try:
            with conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT box_name, target_service, target_os, task, root_cause, lesson
                        FROM error_paths
                        ORDER BY created_at DESC
                        """
                    )
                    rows = cur.fetchall()
        except Exception as e:
            print(f"[ErrorRAG] Index build failed: {e}")
            return False
        finally:
            conn.close()

        if not rows:
            print("[ErrorRAG] No records yet — index empty")
            return False

        corpus = []
        meta   = []
        for r in rows:
            text = (
                f"{r['target_service']} {r['target_os']} "
                f"{r['task']} {r['root_cause']} {r['lesson']}"
            )
            corpus.append(text)
            meta.append(dict(r))

        self._corpus   = corpus
        self._metadata = meta
        self._bm25     = BM25Okapi([_tokenize(c) for c in corpus])
        print(f"[ErrorRAG] Index built: {len(corpus)} records")
        return True

    def query(self, task_description: str, root_cause: str = "", top_k: int = 3) -> str:
        """
        Search error_paths for similar past FUNDAMENTAL failures.
        Returns an injection block for the coordinator prompt, or "" if nothing relevant.
        """
        if self._bm25 is None:
            if not self._build_index():
                return ""

        query_text = f"{task_description} {root_cause}".strip()
        tokens = _tokenize(query_text)
        if not tokens:
            return ""

        scores  = self._bm25.get_scores(tokens)
        top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        top_idx = [i for i in top_idx if scores[i] > 0]
        if not top_idx:
            print(f"[ErrorRAG] No matching records for: {query_text[:60]!r}")
            return ""

        lines = [
            "[Lessons from past failures — check whether the same conditions apply before retrying]",
            "",
        ]
        for n, i in enumerate(top_idx, 1):
            m = self._metadata[i]
            service = m.get("target_service") or "unknown service"
            os_str  = m.get("target_os") or "unknown OS"
            box     = m.get("box_name") or "unknown"
            lines.append(f"{n}. {service} ({box}, {os_str})")
            lines.append(f"   What happened: {m['root_cause']}")
            lines.append(f"   Lesson: {m['lesson']}")
            lines.append("")

        result = "\n".join(lines).rstrip()
        print(f"[ErrorRAG] Returning {len(top_idx)} records for: {query_text[:60]!r}")
        return result
