from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evaluator import create_draft
from src.schemas import FactualityInput, Task


FIXTURES = ROOT / "data" / "factuality_test_tasks.json"
OUTPUT = ROOT / "logs" / "fixture_batch_runs"


def run() -> Path:
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    started = time.perf_counter()
    cases = []
    for fixture in fixtures:
        case_started = time.perf_counter()
        task = Task(
            task_type="factuality",
            factuality=FactualityInput(
                user_query=fixture["user_query"],
                response=fixture["response"],
                target_sentence=fixture["target_sentence"],
                response_date=fixture.get("response_date", ""),
                user_location=fixture.get("user_location", ""),
                user_locale=fixture.get("user_locale", "Portuguese (BR)"),
            ),
        )
        draft = create_draft(task).model_dump()
        cases.append({
            "id": fixture["id"],
            "user_query": fixture["user_query"],
            "claims": len(draft["result_evaluations"]),
            "suggested_rating": draft["task_summary"].get("factuality_rating_suggestion"),
            "pending_evidence": sum(bool(item["evidence_required"]) for item in draft["result_evaluations"]),
            "guideline_citations": len(draft["source_citations"]),
            "duration_ms": round((time.perf_counter() - case_started) * 1000, 2),
        })
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "fixture_count": len(cases),
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "human_ratings": "not supplied - no ratings invented",
        "cases": cases,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    print(run())
