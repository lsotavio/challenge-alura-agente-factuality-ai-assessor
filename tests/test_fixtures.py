import json
from pathlib import Path

from src.evaluator import create_draft
from src.schemas import FactualityInput, Task


def test_eight_factuality_tasks_are_available():
    path = Path(__file__).parents[1] / "data" / "factuality_test_tasks.json"
    tasks = json.loads(path.read_text(encoding="utf-8"))
    assert len(tasks) == 8
    assert all(item["user_query"] and item["response"] and item["target_sentence"] for item in tasks)
    assert len({item["id"] for item in tasks}) == 8


def test_all_fixture_tasks_generate_drafts():
    path = Path(__file__).parents[1] / "data" / "factuality_test_tasks.json"
    tasks = json.loads(path.read_text(encoding="utf-8"))
    drafts = [create_draft(Task(task_type="factuality", factuality=FactualityInput(user_query=item["user_query"], response=item["response"], target_sentence=item["target_sentence"], user_location=item["user_location"], user_locale=item["user_locale"], response_date=item["response_date"]))) for item in tasks]
    assert len(drafts) == 8
    assert all(draft.task_summary["claims_identified"] for draft in drafts)
