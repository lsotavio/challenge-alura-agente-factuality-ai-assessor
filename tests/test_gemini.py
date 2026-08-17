from types import SimpleNamespace

import src.gemini as gemini_module
from src.gemini import GeminiClaimReview, GeminiReview, friendly_gemini_error, merge_review
from src.schemas import Draft, Evaluation, FactualityInput, Task


def test_merge_gemini_keeps_human_review_and_adds_suggestion():
    base = Draft(
        task_summary={"task_type": "Factuality"},
        result_evaluations=[Evaluation(
            id="claim_1",
            factuality_rating="Unsupported",
            reasoning="base",
            confidence="low",
            evidence_required=["Add reputable evidence for this claim."],
        )],
        source_citations=[],
        human_review_checklist=["Approve manually."],
    )
    review = GeminiReview(summary="Há evidência insuficiente.", final_rating="Unsupported", web_citations=[
        {"title": "Official source", "url": "https://www.noaa.gov/example", "source_quality": "primary_authoritative"}
    ], claims=[
        GeminiClaimReview(claim_id="claim_1", rating="Unsupported", reasoning="A fonte não foi fornecida.", evidence_gaps=["Confirmar a fonte."])
    ])
    merged = merge_review(base, review)
    assert merged.task_summary["ai_provider"] == "Google Gemini"
    assert merged.task_summary["human_review_required"] is True
    assert merged.task_summary["gemini_review_status"] == "pending"
    assert "Confirmar a fonte." in merged.result_evaluations[0].evidence_required
    assert "Compare the Gemini suggestion" in merged.human_review_checklist[0]
    assert merged.result_evaluations[0].confidence == "high"
    assert merged.result_evaluations[0].evidence[0]["url"] == "https://www.noaa.gov/example"
    assert "Add reputable evidence for this claim." not in merged.result_evaluations[0].evidence_required


def test_grounding_metadata_collects_tool_queries_and_citations():
    interaction = SimpleNamespace(steps=[
        {"type": "google_search_call", "arguments": {"queries": ["Conselho Alfa anuidade 2025"]}},
        {"type": "model_output", "content": [{
            "type": "text",
            "annotations": [{
                "type": "url_citation",
                "title": "Anuidade de 2025",
                "url": "https://www.gov.br/conselho-alfa/anuidade-2025",
            }],
        }]},
    ])

    citations, queries = gemini_module._grounding_metadata(interaction)

    assert queries == ["Conselho Alfa anuidade 2025"]
    assert citations[0]["url"] == "https://www.gov.br/conselho-alfa/anuidade-2025"
    assert citations[0]["source_quality"] == "primary_authoritative"


def test_merge_applies_suggested_rating_to_unrated_claim():
    base = Draft(
        task_summary={"task_type": "Factuality"},
        result_evaluations=[Evaluation(
            id="claim_1",
            factuality_rating=None,
            reasoning="No rating selected; awaiting assessment.",
            confidence="low",
            evidence_required=["Add reputable evidence for this claim."],
        )],
        source_citations=[],
        human_review_checklist=["Approve manually."],
    )
    review = GeminiReview(
        summary="Não há registro histórico confiável.",
        final_rating="Can't confidently assess",
        claims=[GeminiClaimReview(
            claim_id="claim_1",
            rating="Can't confidently assess",
            reasoning="A previsão passada não pode ser reconstruída com confiança.",
            evidence_gaps=["Registro histórico correspondente à data."],
        )],
    )
    merged = merge_review(base, review)
    evaluation = merged.result_evaluations[0]
    assert evaluation.factuality_rating == "Can't confidently assess"
    assert evaluation.reasoning == "A previsão passada não pode ser reconstruída com confiança."
    assert evaluation.evidence_required == ["Registro histórico correspondente à data."]


def test_gemini_searches_web_and_extracts_citations(monkeypatch):
    captured = {}
    payload = GeminiReview(
        summary="O calendário oficial confirma o jogo.",
        final_rating="Accurate",
        claims=[GeminiClaimReview(claim_id="claim_1", rating="Accurate", reasoning="Confirmado por fonte oficial.")],
    ).model_dump_json()
    interaction = SimpleNamespace(output_text=payload, steps=[])

    class FakeInteractions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return interaction

    monkeypatch.setattr(gemini_module, "_load_client", lambda: SimpleNamespace(interactions=FakeInteractions()))
    monkeypatch.setattr(gemini_module, "search_claim", lambda *args, **kwargs: {
        "queries": ["Equipe Azul Equipe Verde 19 junho 2026"],
        "results": [{"title": "FIFA", "url": "https://www.fifa.com/example", "snippet": "Official schedule", "source": "web", "source_quality": "primary_authoritative", "relevance_score": 12}],
        "errors": [],
    })
    task = Task(task_type="factuality", factuality=FactualityInput(
        user_query="com quem a Equipe Azul vai jogar",
        response="A Equipe Azul enfrenta a Equipe Verde.",
        target_sentence="A Equipe Azul enfrenta a Equipe Verde em 19 de junho de 2026.",
    ))
    review = gemini_module.review_with_gemini(task)
    assert captured["response_format"]["mime_type"] == "application/json"
    assert captured["generation_config"]["thinking_level"] == "medium"
    assert "exclusive rating scope" in captured["input"]
    assert captured["generation_config"]["max_output_tokens"] == 1400
    assert captured["tools"] == [{"type": "google_search"}, {"type": "url_context"}]
    assert review.final_rating == "Accurate"
    assert review.search_queries == ["Equipe Azul Equipe Verde 19 junho 2026"]
    assert review.web_citations == [{"title": "FIFA", "url": "https://www.fifa.com/example", "source_quality": "primary_authoritative", "relevance_score": 12}]


def test_grounded_citations_replace_unverified_local_candidates(monkeypatch):
    payload = GeminiReview(
        summary="A fonte oficial confirma data e adversário.",
        final_rating="Accurate",
    ).model_dump_json()
    interaction = SimpleNamespace(
        output_text=payload,
        steps=[SimpleNamespace(
            type="google_search",
            result=SimpleNamespace(
                search_queries=["site:fifa.com Equipe Azul Equipe Dourada 20 June 2026"],
            ),
        )],
        outputs=[SimpleNamespace(
            type="text",
            annotations=[SimpleNamespace(
                type="url_citation",
                url="https://www.fifa.com/official-match",
                title="Equipe Azul v Equipe Dourada | Federação",
            )],
        )],
    )

    class FakeInteractions:
        def create(self, **kwargs):
            return interaction

    monkeypatch.setattr(gemini_module, "_load_client", lambda: SimpleNamespace(interactions=FakeInteractions()))
    monkeypatch.setattr(gemini_module, "search_claim", lambda *args, **kwargs: {
        "queries": ["Equipe Azul Equipe Dourada"],
        "results": [{
            "title": "Irrelevant local candidate",
            "url": "https://example.com/unrelated",
            "snippet": "Unrelated",
            "source": "web",
            "source_quality": "general_web",
            "relevance_score": 1,
        }],
        "errors": [],
    })
    task = Task(task_type="factuality", factuality=FactualityInput(
        user_query="agenda da equipe azul",
        response="20/06/2026 | Equipe Dourada | Arena Central | Grupo L",
        target_sentence="20/06/2026\nEquipe Dourada",
        highlighted_fragments=["20/06/2026", "Equipe Dourada"],
    ))

    review = gemini_module.review_with_gemini(task)

    assert review.final_rating == "Accurate"
    assert [item["url"] for item in review.web_citations] == ["https://www.fifa.com/official-match"]
    assert "https://example.com/unrelated" not in {item["url"] for item in review.web_citations}


def test_verifiable_claim_without_local_evidence_still_uses_google_search(monkeypatch):
    captured = {}
    payload = GeminiReview(
        summary="Reasonable grounded search found no corroboration.",
        final_rating="Unsupported",
        claims=[GeminiClaimReview(claim_id="claim_1", rating="Unsupported", reasoning="No support found.")],
    ).model_dump_json()

    class FakeInteractions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text=payload, steps=[])

    monkeypatch.setattr(gemini_module, "_load_client", lambda: SimpleNamespace(interactions=FakeInteractions()))
    monkeypatch.setattr(gemini_module, "search_claim", lambda *args, **kwargs: {
        "queries": ["specific claim"],
        "results": [{"title": "manual", "url": "https://google.com", "source": "manual_fallback"}],
        "errors": [],
    })
    task = Task(task_type="factuality", factuality=FactualityInput(
        user_query="specific claim",
        response="response",
        target_sentence="specific claim",
    ))
    review = gemini_module.review_with_gemini(task)
    assert review.final_rating == "Unsupported"
    assert review.web_citations == []
    assert {tool["type"] for tool in captured["tools"]} == {"google_search", "url_context"}


def test_past_weather_without_historical_source_is_cant_confidently_assess(monkeypatch):
    captured = {}
    monkeypatch.setattr(gemini_module, "_load_client", lambda: (_ for _ in ()).throw(AssertionError("must not call Gemini")))

    def fake_search(*args, **kwargs):
        captured.update(kwargs)
        return {
            "queries": ["clima Cidade Aurora 15/03/2025 previsão fim de semana"],
            "results": [{"title": "manual", "url": "https://google.com", "source": "manual_fallback"}],
            "errors": [],
        }

    monkeypatch.setattr(gemini_module, "search_claim", fake_search)
    task = Task(task_type="factuality", factuality=FactualityInput(
        user_query="clima em Cidade Aurora",
        response="Previsão para hoje e próximos dias.",
        target_sentence="Fim de semana com chuva e temperatura média de 24°C.",
        response_date="15/03/2025",
    ))
    review = gemini_module.review_with_gemini(task)
    assert review.final_rating == "Can't confidently assess"
    assert captured["max_queries"] == 1
    assert captured["max_results"] == 2
    assert "registro confiável" in review.summary


def test_quota_error_is_explained_without_raw_payload(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.6-flash")
    message = friendly_gemini_error(RuntimeError("Error code: 429 too_many_requests"))
    assert "cota de inferência" in message
    assert "{'error'" not in message


def test_deprecated_25_override_is_migrated(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    assert gemini_module.gemini_model() == "gemini-3.6-flash"
