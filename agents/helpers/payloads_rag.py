from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from rank_bm25 import BM25Okapi

# Path to the local PayloadsAllTheThings clone (sibling of PLANTE)
_PATT_ROOT = Path(__file__).resolve().parents[3] / "PayloadsAllTheThings"

# Sections to skip — pure TOC/boilerplate, no payload content
_SKIP_HEADERS = {"summary", "references", "labs", "tools", "contributing", "resources"}

# BM25 index built lazily on first query
_corpus:   Optional[list[str]] = None     # raw chunk text
_metadata: Optional[list[dict]] = None    # {category, header} per chunk
_bm25:     Optional[BM25Okapi]  = None


def _tokenize(text: str) -> list[str]:
    # Keep 2-char terms — critical pentest acronyms: rce, id, os, xss, lfi, sqli
    return [t for t in re.split(r"\W+", text.lower()) if len(t) > 1]


def _build_index() -> None:
    global _corpus, _metadata, _bm25

    chunks: list[str]  = []
    meta:   list[dict] = []

    for readme in sorted(_PATT_ROOT.rglob("README.md")):
        category = readme.parent.name
        try:
            text = readme.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Split into sections at ## headers
        sections = re.split(r"\n(?=## )", text)
        for section in sections:
            lines  = section.strip().splitlines()
            if not lines:
                continue
            header = re.sub(r"^#+\s*", "", lines[0]).strip()
            if header.lower() in _SKIP_HEADERS:
                continue
            # Keep up to 1500 chars of content — PATT payload lists need more room
            content = "\n".join(lines[:80])[:1500]
            if len(content) < 40:          # skip near-empty sections
                continue
            chunks.append(f"{category} {header} {content}")
            meta.append({"category": category, "header": header, "content": content})

    _corpus   = chunks
    _metadata = meta
    _bm25     = BM25Okapi([_tokenize(c) for c in chunks])
    print(f"[PayloadsRAG] Index built: {len(chunks)} chunks from {_PATT_ROOT.name}")


def _ensure_index() -> bool:
    if _bm25 is not None:
        return True
    if not _PATT_ROOT.exists():
        print(f"[PayloadsRAG] PATT not found at {_PATT_ROOT} — skipping")
        return False
    _build_index()
    return _bm25 is not None


class PayloadsRAG:
    """
    Lexical RAG (BM25) over a local PayloadsAllTheThings clone.

    Index is built once per process on first query. Each query returns the
    top-k most relevant payload sections as a text block for the coordinator prompt.
    """

    async def query(self, topic: str, top_k: int = 3) -> str:
        if not _ensure_index():
            return ""

        tokens = _tokenize(topic)
        if not tokens:
            return ""

        scores = _bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        # Drop chunks with zero score — no overlap with query at all
        top_indices = [i for i in top_indices if scores[i] > 0]
        if not top_indices:
            print(f"[PayloadsRAG] No relevant chunks for: {topic!r}")
            return ""

        lines = ["=== PayloadsAllTheThings (relevant techniques) ==="]
        for i in top_indices:
            m = _metadata[i]
            lines.append(f"\n[{m['category']}] {m['header']}")
            lines.append(m["content"])

        result = "\n".join(lines)
        print(f"[PayloadsRAG] Returning {len(top_indices)} chunks for: {topic!r}")
        return result
