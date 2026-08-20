from __future__ import annotations

from .assessment import AssessmentPlan
from .retrieval import retrieve
from .schemas import Task


def build_review_prompt(task: Task, assessment_plan: AssessmentPlan | None = None) -> str:
    query = task.query
    task_type = task.task_type
    context_query = query
    if task_type == "factuality" and task.factuality:
        context_query = " ".join(claim.text for claim in task.factuality.claims) or task.factuality.target_sentence
    hits = retrieve(context_query, task_type, limit=6)
    context = "\n\n".join(
        f"[Source: {hit['source']} | page {hit['page']} | section {hit['section']}]\n{hit['text']}"
        for hit in hits
    ) or "No local guideline context was retrieved."
    temporal_instruction = ""
    if assessment_plan and assessment_plan.mode == "limited_temporal":
        temporal_instruction = f"""
Time-sensitive claim rule:
- A short, timestamp-specific research attempt has already been made.
- Reason for limiting research: {assessment_plan.reason}
- Choose Can't confidently assess when the exact state or forecast at the evaluation time cannot
  be reconstructed from a directly relevant, reliable, timestamp-matched source.
- Do not treat a current forecast, current price, current counter, or updated page as evidence for
  what was shown or predicted at an earlier time.
- If a reliable historical record matching the place, date, and claimed value was retrieved, assess
  it normally as Accurate, Inaccurate, or Disputed.
"""
    return f"""You are preparing a human-reviewable Internet Assessor draft.

Task type: {task_type}
User query: {query}
Locale: {task.locale}
Language: {task.language}
User location: {task.user_location or 'not provided'}
Task-specific instructions: {task.task_instructions or 'none'}

Use only the task evidence, supplied Web research and guideline context. Source language
does not need to match the locale; prioritize directly relevant primary and authoritative
sources regardless of language. Do not invent page content, research results, claims, or citations.

Rating boundary rules:
- The highlighted target content is the exclusive rating scope. Surrounding response text supplies
  context only and must not silently expand the claim being rated.
- If the highlight contains multiple fragments or atomic facts, evaluate each one. A contradicted
  target fact makes the overall target Inaccurate even when another target fact is Accurate.
- A retrieved URL is not evidence by itself. Read its extracted excerpt and compare the exact
  entity, predicate, number, date, and qualifier against the highlighted content.
- Can't confidently assess means the claim is theoretically checkable, but the available sources
  cannot support a confident judgment at the required time or with the visible context.
- Unsupported means the claim is understandable and ordinarily checkable, but reasonable research
  found no reputable supporting or contradicting evidence.
- Never choose Can't confidently assess merely because the topic is technical. Lack of reviewer
  expertise is a task-release issue, not a factuality rating.
- Incomplete or hidden target content, an impossible response-date/target-date mismatch, and
  irrecoverable past dynamic data can justify Can't confidently assess. Explain the exact obstacle.
- For dynamic or historical claims, research once before choosing Can't confidently assess.
{temporal_instruction}

Guideline context:
{context}

Return a structured draft with reasoning, evidence gaps, confidence, and exact
source/page/section citations. The human reviewer must approve the result before
any external rating action.
"""
