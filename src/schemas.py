from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


TaskType = Literal["factuality", "severity"]


class FactualityInput(BaseModel):
    user_query: str
    response: str
    target_sentence: str
    response_date: str = ""
    user_location: str = ""
    evidence_notes: str = ""
    evidence_urls: list[str] = []
    factuality_rating: str = ""
    claims: list["ClaimInput"] = []
    user_locale: str = "Portuguese (BR)"


class ClaimInput(BaseModel):
    text: str
    rating: str = ""
    evidence_notes: str = ""
    evidence_urls: list[str] = []
    evidence_items: list["EvidenceItem"] = []


class EvidenceItem(BaseModel):
    url: str = ""
    excerpt: str = ""
    relation: Literal["supports", "contradicts", "context"] = "supports"
    source_quality: Literal["primary", "reputable_secondary", "uncertain"] = "reputable_secondary"
    title: str = ""
    snippet: str = ""


class SeverityInput(BaseModel):
    user_query: str
    target_content: str
    factuality_rating: str = "Inaccurate"
    severity_rating: str = "Medium"
    impact_notes: str = ""
    evidence_notes: str = ""


class Task(BaseModel):
    task_type: TaskType = "factuality"
    query: str = ""
    locale: str = "pt-BR"
    language: str = "Portuguese"
    user_location: str = ""
    task_instructions: str = ""
    factuality: FactualityInput | None = None
    severity: SeverityInput | None = None


class Evaluation(BaseModel):
    id: str
    factuality_rating: str | None = None
    severity_rating: str | None = None
    evidence: list[str | dict] = []
    reasoning: str
    confidence: Literal["high", "medium", "low"]
    evidence_required: list[str] = []


class Draft(BaseModel):
    task_summary: dict
    result_evaluations: list[Evaluation]
    source_citations: list[dict]
    human_review_checklist: list[str]
