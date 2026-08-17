from src.evaluator import create_draft
from src.schemas import ClaimInput, EvidenceItem, FactualityInput, Task
from src.storage import save_session


def test_factuality_requires_claim_research_before_final_rating():
    task = Task(
        task_type="factuality",
        factuality=FactualityInput(
            user_query="Who won the 2023 NBA championship?",
            response="The Denver Nuggets won the 2023 NBA championship.",
            target_sentence="The Denver Nuggets won the 2023 NBA championship.",
        ),
    )
    draft = create_draft(task)
    assert draft.task_summary["factuality_rating_suggestion"] == "Awaiting assessment"
    assert draft.result_evaluations[0].evidence_required


def test_factuality_preserves_rater_hub_context_fields():
    task = Task(
        task_type="factuality",
        factuality=FactualityInput(
            user_query="clima em Cidade Aurora",
            response="O clima em Cidade Aurora está quente. Fim de semana: temperatura média de 24C.",
            target_sentence="Fim de semana: temperatura média de 24C.",
            response_date="18/02/2026",
            user_location="",
            user_locale="Portuguese (BR)",
        ),
    )
    draft = create_draft(task)
    assert draft.task_summary["user_locale"] == "Portuguese (BR)"
    assert draft.task_summary["response_date"] == "18/02/2026"
    assert draft.task_summary["claims_identified"] == ["Fim de semana: temperatura média de 24C."]


def test_structured_evidence_is_preserved_per_claim():
    task = Task(
        task_type="factuality",
        factuality=FactualityInput(
            user_query="q",
            response="r",
            target_sentence="claim",
            claims=[ClaimInput(
                text="claim",
                rating="Disputed",
                evidence_items=[EvidenceItem(url="https://example.com", excerpt="Relevant excerpt", relation="contradicts", source_quality="primary")],
            )],
        ),
    )
    evaluation = create_draft(task).result_evaluations[0]
    assert evaluation.evidence[0]["relation"] == "contradicts"
    assert evaluation.evidence[0]["source_quality"] == "primary"
    assert not evaluation.evidence_required


def test_general_evidence_is_attached_to_highlighted_claim():
    task = Task(
        task_type="factuality",
        factuality=FactualityInput(
            user_query="clima em Cidade Aurora",
            response="context",
            target_sentence="Fim de semana com 27C",
            factuality_rating="Can't confidently assess",
            evidence_notes="Historical forecast cannot be checked retroactively.",
        ),
    )
    evaluation = create_draft(task).result_evaluations[0]
    assert "Historical forecast cannot be checked retroactively." in evaluation.evidence
    assert not evaluation.evidence_required


def test_factuality_has_individual_claims():
    task = Task(
        task_type="factuality",
        factuality=FactualityInput(
            user_query="q",
            response="r",
            target_sentence="a and b",
            claims=[ClaimInput(text="a", rating="Accurate"), ClaimInput(text="b", rating="Unsupported")],
        ),
    )
    draft = create_draft(task)
    assert [item.id for item in draft.result_evaluations] == ["claim_1", "claim_2"]
    assert draft.task_summary["factuality_rating_suggestion"] == "Unsupported"





def test_session_is_saved_as_auditable_json(tmp_path, monkeypatch):
    import src.storage as storage
    monkeypatch.setattr(storage, "SESSIONS_DIR", tmp_path)
    path = save_session({"task_type": "factuality"}, {"task_summary": {}}, "approved", "test-session")
    payload = path.read_text(encoding="utf-8")
    assert path.exists()
    assert '"status": "approved"' in payload
    assert '"session_id": "test-session"' in payload
