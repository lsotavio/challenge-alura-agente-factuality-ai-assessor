import json

import src.retrieval as retrieval
from src.prompting import build_review_prompt
from src.schemas import Task


def test_retrieve_uses_structured_metadata(tmp_path, monkeypatch):
    index = tmp_path / "guidelines.json"
    index.write_text(json.dumps({"chunks": [{
        "source": "synthetic_guide.pdf",
        "page": 10,
        "section": "5.0 Factuality Rating Guideline",
        "task_type": "factuality",
        "keywords": ["accurate", "claims", "evidence"],
        "text": "Accurate claims require reputable evidence."
    }]}), encoding="utf-8")
    monkeypatch.setattr(retrieval, "INDEX_PATH", index)
    hits = retrieval.retrieve("accurate claims evidence", "factuality")
    assert hits[0]["page"] == 10
    assert hits[0]["section"] == "5.0 Factuality Rating Guideline"


def test_review_prompt_contains_retrieved_source(monkeypatch):
    monkeypatch.setattr(retrieval, "INDEX_PATH", retrieval.INDEX_PATH)
    task = Task(task_type="factuality", query="claims")
    prompt = build_review_prompt(task)
    assert "human-reviewable" in prompt


def test_retrieve_falls_back_to_normative_context_when_language_differs(tmp_path, monkeypatch):
    index = tmp_path / "guidelines.json"
    index.write_text(json.dumps({"chunks": [
        {"source": "factuality.pdf", "page": 2, "section": "1.0 Overview", "task_type": "factuality", "keywords": ["overview"], "text": "Identify claims, research evidence, and assess factuality."},
        {"source": "factuality.pdf", "page": 10, "section": "5.0 Factuality Rating", "task_type": "factuality", "keywords": ["rating"], "text": "Accurate, Unsupported, Disputed."}
    ]}), encoding="utf-8")
    monkeypatch.setattr(retrieval, "INDEX_PATH", index)
    hits = retrieval.retrieve("uma pergunta em português sem os termos ingleses", "factuality")
    assert hits
    assert hits[0]["section"] in {"1.0 Overview", "5.0 Factuality Rating"}
