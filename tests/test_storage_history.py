import json
from datetime import datetime, timezone

import pytest

from src import storage
from src.storage import (
    HistoryImportError,
    create_history_export,
    form_state_from_session,
    import_history_export,
)


def test_public_mode_does_not_persist_or_list_tasks(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PERSIST_TASK_HISTORY", "false")
    monkeypatch.setattr(storage, "SESSIONS_DIR", tmp_path)

    path = storage.save_session({"query": "private"}, {"task_summary": {}}, "draft")

    assert path.parent == tmp_path
    assert not path.exists()
    assert storage.list_sessions() == []
    assert list(tmp_path.iterdir()) == []


def test_saved_session_can_restore_the_task_form_and_result() -> None:
    session = {
        "session_id": "session-123",
        "task": {
            "query": "fallback query",
            "user_location": "",
            "factuality": {
                "user_query": "clima em Cidade de Teste",
                "response": "Resposta completa",
                "target_sentence": "Trecho destacado",
                "response_date": "18/02/2026",
                "user_location": "",
                "user_locale": "Portuguese (BR)",
            },
        },
        "draft": {"task_summary": {"gemini_final_rating": "Accurate"}},
    }

    restored = form_state_from_session(session)

    assert restored["f_query"] == "clima em Cidade de Teste"
    assert restored["f_response"] == "Resposta completa"
    assert restored["f_target"] == "Trecho destacado"
    assert restored["f_location"] == ""
    assert restored["draft"] == session["draft"]
    assert restored["session_id"] == "session-123"


def test_history_export_has_versioned_format_and_timestamped_name() -> None:
    now = datetime(2026, 8, 19, 14, 35, 22, tzinfo=timezone.utc)
    filename, content = create_history_export([{"session_id": "one"}], now)
    payload = json.loads(content)

    assert filename == "assistente-de-factualidade-historico-2026-08-19_14-35-22.json"
    assert payload["format"] == "assistente-de-factualidade-history"
    assert payload["version"] == 1
    assert payload["sessions"] == [{"session_id": "one"}]


def test_history_import_merges_and_skips_existing_sessions(tmp_path, monkeypatch) -> None:
    import src.storage as storage

    monkeypatch.setattr(storage, "SESSIONS_DIR", tmp_path)
    existing = {"session_id": "existing", "task": {}, "draft": {}}
    (tmp_path / "existing.json").write_text(json.dumps(existing), encoding="utf-8")
    sessions = [existing, {"session_id": "new-session", "task": {}, "draft": {}, "status": "approved"}]
    _, content = create_history_export(sessions)

    result = import_history_export(content)

    assert result == {"imported": 1, "skipped": 1}
    assert json.loads((tmp_path / "new-session.json").read_text(encoding="utf-8"))["status"] == "approved"


def test_history_import_rejects_unknown_or_unsafe_files(tmp_path, monkeypatch) -> None:
    import src.storage as storage

    monkeypatch.setattr(storage, "SESSIONS_DIR", tmp_path)
    with pytest.raises(HistoryImportError):
        import_history_export(b'{"sessions": []}')
    malicious = {
        "format": storage.HISTORY_FORMAT,
        "version": 1,
        "sessions": [{"session_id": "../escape", "task": {}, "draft": {}}],
    }
    with pytest.raises(HistoryImportError):
        import_history_export(json.dumps(malicious))
    assert not list(tmp_path.glob("*"))
