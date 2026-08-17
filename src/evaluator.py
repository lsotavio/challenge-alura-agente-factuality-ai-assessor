from __future__ import annotations

from .retrieval import retrieve
from .schemas import ClaimInput, Draft, Evaluation, Task


FACTUALITY_RATINGS = [
    "Inaccurate",
    "Unsupported",
    "Disputed",
    "Accurate",
    "Can't confidently assess",
    "No claims present",
]


def create_draft(task: Task) -> Draft:
    return create_factuality_draft(task)


def create_factuality_draft(task: Task) -> Draft:
    factuality = task.factuality
    if factuality is None:
        raise ValueError("Factuality input is required for a factuality task.")
    target = factuality.target_sentence.strip()
    claims = [claim for claim in factuality.claims if claim.text.strip()]
    if not claims and target:
        claims = [ClaimInput(
            text=target,
            rating=factuality.factuality_rating,
            evidence_notes=factuality.evidence_notes,
            evidence_urls=factuality.evidence_urls,
        )]
    if not target:
        rating = "Can't confidently assess"
        claim_texts = []
        reasoning = "A target sentence is required before claims can be identified."
    else:
        claim_texts = [claim.text for claim in claims]
        rating = factuality.factuality_rating or "Awaiting assessment"
        reasoning = (
            f"Selected factuality rating: {rating}. Review each claim independently and record supporting or contradicting evidence."
        )
    claim_evaluations = []
    source_citations = []
    for index, claim in enumerate(claims, start=1):
        claim_id = f"claim_{index}"
        claim_notes = claim.evidence_notes
        claim_urls = list(claim.evidence_urls)
        if index == 1:
            claim_notes = claim_notes or factuality.evidence_notes
            claim_urls = claim_urls or factuality.evidence_urls
        retrieved = retrieve(claim.text, "factuality", limit=3)
        for hit in retrieved:
            source_citations.append({"claim_id": claim_id, **hit})
        structured_evidence = []
        for item in claim.evidence_items:
            structured_evidence.append({
                "url": item.url,
                "title": item.title,
                "snippet": item.snippet,
                "excerpt": item.excerpt,
                "relation": item.relation,
                "source_quality": item.source_quality,
            })
        selected_text = claim.rating or "No rating selected; awaiting assessment."
        claim_evaluations.append(Evaluation(
            id=claim_id,
            factuality_rating=claim.rating or None,
            evidence=claim_urls + ([claim_notes] if claim_notes else []) + structured_evidence,
            reasoning=f"Claim {index}: {claim.text}. {selected_text}",
            confidence="medium" if claim.evidence_urls or claim.evidence_notes or structured_evidence else "low",
            evidence_required=[] if claim_urls or claim_notes or claim.evidence_items else ["Add reputable evidence for this claim."],
        ))
    if not claim_evaluations:
        claim_evaluations = [Evaluation(
            id="target_sentence",
            factuality_rating=rating,
            evidence=[],
            reasoning=reasoning,
            confidence="low",
            evidence_required=["Identify the claims in the target sentence."],
        )]
    rating_order = ["Inaccurate", "Unsupported", "Disputed", "Accurate", "Can't confidently assess", "No claims present"]
    selected_ratings = [claim.rating for claim in claims if claim.text.strip()]
    if not selected_ratings:
        rating = "Awaiting assessment" if target else "No claims present"
    elif factuality.factuality_rating == "No claims present":
        rating = "No claims present"
    else:
        rating = next((candidate for candidate in rating_order if candidate in selected_ratings), factuality.factuality_rating or "Awaiting assessment")
    
    return Draft(
        task_summary={
            "task_type": "Factuality",
            "user_query": factuality.user_query,
            "response_date": factuality.response_date,
            "user_location": factuality.user_location,
            "user_locale": factuality.user_locale,
            "claims_identified": claim_texts,
            "factuality_rating_suggestion": rating,

        },
        result_evaluations=claim_evaluations,
        source_citations=source_citations,
        human_review_checklist=[
            "Confirm which parts of the target sentence are checkable factual claims.",
            "Treat reasonable subjective claims as accurate unless evidence shows otherwise.",
            "Prefer primary, authoritative, current and context-appropriate sources.",
            "Reconcile disagreements; do not label a claim disputed without irreconcilable evidence.",

            "Approve manually; the agent does not submit ratings.",
        ],
    )
