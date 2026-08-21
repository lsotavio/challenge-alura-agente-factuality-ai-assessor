from __future__ import annotations

import json
import os
from pathlib import Path
from time import perf_counter
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .assessment import plan_assessment
from .highlights import scoped_target
from .prompting import build_review_prompt
from .research import search_claim, source_quality
from .schemas import Draft, Task


class GeminiClaimReview(BaseModel):
    claim_id: str
    rating: Literal[
        "Inaccurate",
        "Unsupported",
        "Disputed",
        "Accurate",
        "Can't confidently assess",
        "No claims present",
        "Not applicable",
    ] = Field(description="Use exactly one official factuality rating.")
    reasoning: str
    evidence_gaps: list[str] = Field(default_factory=list)


class GeminiReview(BaseModel):
    summary: str
    final_rating: Literal[
        "Inaccurate",
        "Unsupported",
        "Disputed",
        "Accurate",
        "Can't confidently assess",
        "No claims present",
        "Not applicable",
    ] = "Not applicable"

    claims: list[GeminiClaimReview] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    web_citations: list[dict[str, str | int]] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    latency_ms: int = 0


class GeminiUnavailable(RuntimeError):
    pass


def gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def gemini_model() -> str:
    # Gemini 2.5 Flash keeps Google Search/URL Context while offering a much
    # larger free allowance than the highly restricted Gemini 3 preview tier.
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"


def friendly_gemini_error(exc: Exception) -> str:
    message = str(exc)
    if "timeout" in message.lower() or "timed out" in message.lower():
        return "O Gemini ultrapassou o limite de 45 segundos. A chamada foi encerrada; tente novamente mais tarde."
    if "429" in message or "too_many_requests" in message or "RESOURCE_EXHAUSTED" in message:
        return (
            "A cota de inferência da API foi atingida. Aguarde a renovação indicada no Google AI Studio "
            "ou confira se esta chave pertence ao projeto correto. Nenhuma nova tentativa foi feita automaticamente."
        )
    if "404" in message or "not_found" in message.lower():
        return "O modelo configurado não está disponível para esta chave. O agente usa gemini-2.5-flash por padrão."
    if "401" in message or "403" in message:
        return "A chave não tem acesso à API ou ao modelo selecionado. Confira a chave e o projeto no Google AI Studio."
    return "A análise não pôde ser concluída. Confira a conexão e as configurações da API Gemini."


def _load_client():
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise GeminiUnavailable("Instale a dependência google-genai para usar o Gemini.") from exc
    if not gemini_configured():
        raise GeminiUnavailable("GEMINI_API_KEY não está configurada.")
    timeout_ms = int(os.getenv("GEMINI_TIMEOUT_MS", "45000"))
    return genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        http_options=types.HttpOptions(
            timeout=timeout_ms,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def _parse_review(text: str) -> GeminiReview:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        return GeminiReview.model_validate_json(cleaned)
    except Exception:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return GeminiReview.model_validate_json(cleaned[start:end + 1])
        raise


def log_gemini_error(exc: Exception) -> None:
    path = Path(__file__).resolve().parents[1] / "logs" / "gemini_errors.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "at": datetime.now(timezone.utc).isoformat(),
        "model": gemini_model(),
        "error_type": type(exc).__name__,
        "error": str(exc)[:1500],
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _grounding_metadata(interaction) -> tuple[list[dict], list[str]]:
    """Collect citations and queries emitted by Gemini built-in Web tools."""
    citations: list[dict] = []
    queries: list[str] = []

    def visit(value) -> None:
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        elif hasattr(value, "__dict__"):
            value = vars(value)
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        item_type = str(value.get("type", ""))
        url = value.get("url") or value.get("uri")
        if url and item_type in {"url_citation", "google_search_result", "url_context_result"}:
            citations.append({
                "title": value.get("title") or value.get("name") or url,
                "url": url,
                "source_quality": source_quality(url),
                "relevance_score": 0,
            })
        if item_type in {"google_search_call", "google_search"}:
            arguments = value.get("arguments") or {}
            result = value.get("result") or {}
            if hasattr(result, "model_dump"):
                result = result.model_dump(mode="json")
            elif hasattr(result, "__dict__"):
                result = vars(result)
            candidates = (
                arguments.get("queries")
                or result.get("search_queries")
                or [arguments.get("query")]
            )
            queries.extend(str(query) for query in candidates if query)
        for nested in value.values():
            visit(nested)

    visit(interaction)
    return list({item["url"]: item for item in citations}.values()), list(dict.fromkeys(queries))


def review_with_gemini(task: Task) -> GeminiReview:
    started = perf_counter()
    model = gemini_model()
    assessment_plan = plan_assessment(task)
    research = {"queries": [], "results": [], "errors": []}
    if task.task_type == "factuality" and task.factuality:
        research = search_claim(
            scoped_target(task.factuality.response, task.factuality.target_sentence),
            task.factuality.user_query,
            task.factuality.user_location,
            task.factuality.response_date,
            max_results=assessment_plan.max_results,
            max_queries=assessment_plan.max_queries,
            temporal_date=(task.factuality.response_date if assessment_plan.mode == "limited_temporal" else ""),
        )
    usable_sources = [item for item in research["results"] if item.get("source") != "manual_fallback"]
    if task.task_type == "factuality" and not usable_sources and assessment_plan.mode == "limited_temporal":
        temporal = assessment_plan.mode == "limited_temporal"
        rating = "Can't confidently assess" if temporal else "Unsupported"
        if temporal:
            summary = (
                "A busca temporal limitada não encontrou um registro confiável que reproduza "
                "a informação no momento exigido pela tarefa."
            )
            reasoning = (
                "A afirmação é dinâmica e teoricamente verificável, mas não foi recuperada uma "
                "fonte confiável, diretamente relevante e correspondente à data da avaliação."
            )
            gap = "Registro histórico confiável correspondente ao local, à data e ao horário da claim."
        else:
            summary = (
                "A afirmação é compreensível e verificável, mas a busca não encontrou evidência "
                "confiável que a sustentasse ou contradissesse."
            )
            reasoning = (
                "A pesquisa automática razoável não encontrou fonte reputável de apoio nem de "
                "contradição; isso caracteriza falta de evidência, não impossibilidade de avaliação."
            )
            gap = "Fonte reputável que sustente ou contradiga diretamente a afirmação."
        return GeminiReview(
            summary=summary,
            final_rating=rating,
            claims=[GeminiClaimReview(
                claim_id="claim_1",
                rating=rating,
                reasoning=reasoning,
                evidence_gaps=[gap],
            )],
            evidence_gaps=[gap],
            search_queries=research["queries"],
            latency_ms=round((perf_counter() - started) * 1000),
        )
    client = _load_client()
    prompt = (
        build_review_prompt(task, assessment_plan)
        + "\n\nTask payload:\n"
        + json.dumps(task.model_dump(mode="json"), ensure_ascii=False, indent=2)
        + "\n\nWeb research retrieved locally:\n"
        + json.dumps({"sources": usable_sources, "search_errors": research["errors"]}, ensure_ascii=False, indent=2)
        + "\n\nUse the retrieved Web sources plus the enabled Google Search and URL Context tools as factual evidence. "
        + "The highlighted target fragments are the exclusive rating scope. Use the full response only to "
        + "interpret those fragments. Never add a location, group, competition, qualifier, or nearby table cell "
        + "to the rated claim unless that exact text is highlighted. When highlights are discontinuous, assess "
        + "only the factual relationship jointly expressed by those fragments in context. "
        + "Inspect each retrieved excerpt, not merely its title or search snippet. If a relevant page was retrieved, "
        + "do not choose Unsupported before evaluating its extracted page content. Split phone numbers, dates, "
        + "prices, names, and other independently checkable facts inside the target. If any target subclaim is "
        + "directly contradicted, the overall rating is Inaccurate and the reasoning must distinguish which parts "
        + "were confirmed and which were contradicted. "
        + "You must use Google Search when local retrieval is missing, incomplete, or does not expose the exact "
        + "highlighted value. Use URL Context to read promising first-party or authoritative pages before rating. "
        + "Source language is irrelevant: English sources are fully acceptable for a pt-BR task. "
        + "Prefer primary_authoritative sources over lower-quality sources. A directly relevant official source "
        + "may be sufficient by itself. Never use a source merely because it shares a date or generic topic word. "
        + "Do not treat absence of evidence in the task payload as proof that a claim is false. "
        + "Prefer official and primary sources, verify dates and locations, and distinguish "
        + "Unsupported from Inaccurate exactly as the guideline defines them. "
        + "Return only one valid JSON object matching this schema:\n"
        + json.dumps(GeminiReview.model_json_schema(), ensure_ascii=False)
        + "\nNever wrap the JSON in Markdown and never invent citations."
    )
    request = {
        "model": model,
        "input": prompt,
        "tools": [{"type": "google_search"}, {"type": "url_context"}],
        "generation_config": {"max_output_tokens": 1400},
    }
    if model.startswith("gemini-3"):
        request["generation_config"]["thinking_level"] = "medium"
        request["response_format"] = {
            "type": "text",
            "mime_type": "application/json",
            "schema": GeminiReview.model_json_schema(),
        }
    interaction = client.interactions.create(**request)
    review = _parse_review(interaction.output_text)
    local_citations = [
        {
            "title": item["title"],
            "url": item["url"],
            "source_quality": item["source_quality"],
            "relevance_score": item["relevance_score"],
        }
        for item in usable_sources
    ]
    grounded_citations, grounded_queries = _grounding_metadata(interaction)
    # Prefer citations actually returned by Gemini's grounded Google research.
    # Local DDGS results are only candidates supplied to the model and may be
    # tangential; expose them in the UI only when grounding returned nothing.
    selected_citations = grounded_citations or local_citations
    review.web_citations = list({
        item["url"]: item for item in selected_citations
    }.values())
    review.search_queries = list(dict.fromkeys([*research["queries"], *grounded_queries]))
    review.latency_ms = round((perf_counter() - started) * 1000)
    return review


def merge_review(base: Draft, review: GeminiReview) -> Draft:
    """Merge suggestions without replacing deterministic evidence or guardrails."""
    draft = base.model_copy(deep=True)
    draft.task_summary = {
        **draft.task_summary,
        "gemini_summary": review.summary,
        "gemini_final_rating": review.final_rating,

        "gemini_web_citations": review.web_citations,
        "gemini_search_queries": review.search_queries,
        "gemini_latency_ms": review.latency_ms,
        "ai_provider": "Google Gemini",
        "human_review_required": True,
        "gemini_review_status": "pending",
    }
    if draft.task_summary.get("task_type") == "Factuality" and review.final_rating != "Not applicable":
        draft.task_summary["factuality_rating_suggestion"] = review.final_rating
    by_id = {item.claim_id: item for item in review.claims}
    citation_evidence = [
        {
            "title": source.get("title", ""),
            "url": source.get("url", ""),
            "source_quality": source.get("source_quality", "general_web"),
        }
        for source in review.web_citations
    ]
    for evaluation in draft.result_evaluations:
        suggestion = by_id.get(evaluation.id)
        if suggestion:
            evaluation.reasoning = suggestion.reasoning
            evaluation.evidence_required = [
                gap for gap in evaluation.evidence_required
                if gap != "Add reputable evidence for this claim."
            ]
            evaluation.evidence_required.extend(suggestion.evidence_gaps)
            if suggestion.rating:
                evaluation.factuality_rating = suggestion.rating
            if citation_evidence:
                evaluation.evidence.extend(citation_evidence)
                if any(source.get("source_quality") == "primary_authoritative" for source in review.web_citations):
                    evaluation.confidence = "high"
        elif review.evidence_gaps:
            evaluation.evidence_required.extend(review.evidence_gaps)
    draft.human_review_checklist = [
        "Compare the Gemini suggestion against the task evidence and guideline citations.",
        *draft.human_review_checklist,
    ]
    return draft
