from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "data" / "index" / "guidelines.json"


def _terms(text: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[\w-]{4,}", text)}


def _load_index() -> list[dict]:
    if not INDEX_PATH.exists():
        return []
    try:
        payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        return payload.get("chunks", [])
    except (OSError, json.JSONDecodeError):
        return []


def retrieve(query: str, task_type: str = "factuality", limit: int = 4) -> list[dict]:
    """Search the prebuilt local index of Factuality Guidelines; never blocks to reread PDFs during requests."""
    chunks = _load_index()
    query_terms = _terms(query)
    candidates = [chunk for chunk in chunks if chunk.get("task_type") in {"factuality", "general"}]

    scored = []
    for chunk in candidates:
        keyword_set = set(chunk.get("keywords", []))
        score = len(query_terms & keyword_set)
        section_bonus = 2 if any(term in chunk["section"].lower() for term in query_terms) else 0
        scored.append((score + section_bonus, chunk))
    scored.sort(key=lambda item: (item[0], -item[1]["page"]), reverse=True)
    hits = [
        {"source": chunk["source"], "page": chunk["page"], "section": chunk["section"], "score": score, "text": chunk["text"][:1600]}
        for score, chunk in scored[:limit]
        if score > 0
    ]
    if not hits and candidates:
        priority_terms = ("Overview", "Identifying Claims", "Researching Claims", "Factuality Rating", "Severity")
        prioritized = [
            chunk for chunk in candidates
            if any(term.lower() in chunk.get("section", "").lower() for term in priority_terms)
        ]
        fallback = prioritized or candidates[:limit]
        hits = [
            {"source": chunk["source"], "page": chunk["page"], "section": chunk["section"], "score": 0, "text": chunk["text"][:1600]}
            for chunk in fallback[:limit]
        ]
    return hits
