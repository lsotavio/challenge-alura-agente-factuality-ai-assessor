from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SESSIONS_DIR = ROOT / "logs" / "sessions"
HISTORY_FORMAT = "assistente-de-factualidade-history"
HISTORY_VERSION = 1
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


class HistoryImportError(ValueError):
    pass


def history_enabled() -> bool:
    """Return whether task data may be persisted on this installation."""
    return os.getenv("PERSIST_TASK_HISTORY", "true").strip().lower() in {"1", "true", "yes", "on"}


def save_session(task: dict, draft: dict, status: str = "draft", session_id: str | None = None) -> Path:
    session_id = session_id or f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    path = SESSIONS_DIR / f"{session_id}.json"
    if not history_enabled():
        return path
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"session_id": session_id, "saved_at": datetime.now(timezone.utc).isoformat(), "status": status, "task": task, "draft": draft}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_sessions() -> list[dict]:
    if not history_enabled() or not SESSIONS_DIR.exists():
        return []
    sessions = []
    for path in sorted(SESSIONS_DIR.glob("*.json"), reverse=True):
        try:
            sessions.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return sessions


def form_state_from_session(session: dict) -> dict:
    """Map an archived session back to the small set of fields used by the UI."""
    task = session.get("task") or {}
    factuality = task.get("factuality") or {}
    return {
        "f_query": factuality.get("user_query") or task.get("query") or "",
        "f_response": factuality.get("response") or "",
        "f_target": factuality.get("target_sentence") or "",
        "f_location": factuality.get("user_location") or task.get("user_location") or "",
        "f_locale": factuality.get("user_locale") or "Portuguese (BR)",
        "f_date": factuality.get("response_date") or "",
        "task": task,
        "draft": session.get("draft") or {},
        "session_id": session.get("session_id") or "",
    }


def create_history_export(sessions: list[dict] | None = None, now: datetime | None = None) -> tuple[str, bytes]:
    """Create a portable, versioned backup without credentials or application settings."""
    exported_at = now or datetime.now().astimezone()
    payload = {
        "format": HISTORY_FORMAT,
        "version": HISTORY_VERSION,
        "agent": "Assistente de Factualidade",
        "exported_at": exported_at.isoformat(),
        "sessions": list_sessions() if sessions is None else sessions,
    }
    filename = f"assistente-de-factualidade-historico-{exported_at.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return filename, content


def import_history_export(content: bytes | str) -> dict[str, int]:
    """Validate and merge a history backup, skipping session IDs already stored."""
    if not history_enabled():
        raise HistoryImportError("O histórico persistente está desativado nesta instalação pública.")
    raw = content.encode("utf-8") if isinstance(content, str) else content
    if len(raw) > 10 * 1024 * 1024:
        raise HistoryImportError("O arquivo ultrapassa o limite de 10 MB.")
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HistoryImportError("O arquivo não contém um JSON válido.") from exc

    if not isinstance(payload, dict) or payload.get("format") != HISTORY_FORMAT:
        raise HistoryImportError("Este arquivo não é um histórico do Assistente de Factualidade.")
    if payload.get("version") != HISTORY_VERSION:
        raise HistoryImportError("A versão deste histórico ainda não é compatível.")
    sessions = payload.get("sessions")
    if not isinstance(sessions, list) or len(sessions) > 5000:
        raise HistoryImportError("A lista de tarefas do arquivo é inválida.")

    validated = []
    seen_ids = set()
    for session in sessions:
        if not isinstance(session, dict):
            raise HistoryImportError("Uma das tarefas do arquivo está corrompida.")
        session_id = session.get("session_id")
        if not isinstance(session_id, str) or not _SESSION_ID_RE.fullmatch(session_id):
            raise HistoryImportError("Uma das tarefas possui um identificador inválido.")
        if session_id in seen_ids:
            raise HistoryImportError("O arquivo contém tarefas duplicadas.")
        if not isinstance(session.get("task"), dict) or not isinstance(session.get("draft"), dict):
            raise HistoryImportError("Uma das tarefas não possui os dados necessários.")
        seen_ids.add(session_id)
        validated.append(session)

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    imported = 0
    skipped = 0
    for session in validated:
        path = SESSIONS_DIR / f"{session['session_id']}.json"
        if path.exists():
            skipped += 1
            continue
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
        imported += 1
    return {"imported": imported, "skipped": skipped}
