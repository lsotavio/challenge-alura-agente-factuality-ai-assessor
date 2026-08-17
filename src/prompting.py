from __future__ import annotations

from .retrieval import retrieve
from .schemas import Task


def build_review_prompt(task: Task) -> str:
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
    return f"""You are preparing a human-reviewable Internet Assessor draft.

Task type: {task_type}
User query: {query}
Locale: {task.locale}
Language: {task.language}
User location: {task.user_location or 'not provided'}
Task-specific instructions: {task.task_instructions or 'none'}

Use only the task evidence, supplied Web research and guideline context. Source language
does not need to match the locale; prioritize directly relevant primary and authoritative
sources regardless of language. Do not invent page content, research results, claims, or citations. Keep factuality and severity
separate: factuality asks whether a claim is supported; severity asks how an
inaccuracy affects the user's intent.

Guideline context:
{context}

Return a structured draft with reasoning, evidence gaps, confidence, and exact
source/page/section citations. The human reviewer must approve the result before
any external rating action.
"""
