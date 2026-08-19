from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from .schemas import Task


ResearchMode = Literal["standard", "limited_temporal"]


@dataclass(frozen=True)
class AssessmentPlan:
    mode: ResearchMode
    reason: str = ""
    max_queries: int = 2
    max_results: int = 4


WEATHER_TERMS = {
    "clima", "chuva", "chuvas", "nublado", "nuvens", "previsao", "temperatura",
    "tempo", "trovoada", "trovoadas", "weather", "forecast", "rain", "temperature",
}

FORECAST_TERMS = {
    "amanha", "hoje", "noite", "proximos dias", "fim de semana", "tendencia",
    "previsao", "prevista", "preve", "forecast", "tomorrow", "tonight", "weekend",
}

VOLATILE_TERMS = {
    "visualizacoes", "comentarios", "curtidas", "seguidores", "views", "comments",
    "likes", "followers", "preco", "cotacao", "acoes", "indice", "price", "stock",
    "dow jones", "ouro", "gold",
}


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _has_any(subject: str, terms: set[str]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", subject) for term in terms)


def _parse_response_date(value: str) -> date | None:
    compact = value.strip().replace(",", "")
    if not compact:
        return None
    for pattern in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(compact, pattern).date()
        except ValueError:
            continue
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", compact)
    if match:
        try:
            return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        except ValueError:
            return None
    return None


def plan_assessment(task: Task, today: date | None = None) -> AssessmentPlan:
    """Choose a bounded research strategy without deciding factuality prematurely."""
    if task.task_type != "factuality" or task.factuality is None:
        return AssessmentPlan(mode="standard")

    factuality = task.factuality
    subject = _fold(" ".join([
        factuality.user_query,
        factuality.target_sentence,
        factuality.response,
    ]))
    is_weather_forecast = _has_any(subject, WEATHER_TERMS) and _has_any(subject, FORECAST_TERMS)
    is_volatile_snapshot = _has_any(subject, VOLATILE_TERMS)
    if not (is_weather_forecast or is_volatile_snapshot):
        return AssessmentPlan(mode="standard")

    response_day = _parse_response_date(factuality.response_date)
    current_day = today or date.today()
    if response_day is None:
        return AssessmentPlan(
            mode="limited_temporal",
            reason="The claim is time-sensitive, but no reliable evaluation date was supplied.",
            max_queries=1,
            max_results=2,
        )
    if response_day <= current_day:
        category = "weather forecast" if is_weather_forecast else "dynamic point-in-time value"
        return AssessmentPlan(
            mode="limited_temporal",
            reason=f"The claim is a past {category} that requires a timestamp-matched historical record.",
            max_queries=1,
            max_results=2,
        )
    return AssessmentPlan(mode="standard")
