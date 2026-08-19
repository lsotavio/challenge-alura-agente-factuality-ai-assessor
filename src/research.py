from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from urllib.parse import quote_plus, urlparse


STOPWORDS = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos", "e", "em", "foi",
    "na", "nas", "no", "nos", "o", "os", "ou", "para", "pela", "pelo", "por", "que", "se", "ser",
    "sua", "seu", "um", "uma", "the", "a", "an", "and", "as", "at", "by", "for", "from", "in",
    "is", "of", "on", "or", "that", "to", "was", "were", "with", "this", "these", "those",
}

AUTHORITATIVE_DOMAINS = {
    "noaa.gov", "nasa.gov", "nih.gov", "cdc.gov", "who.int", "un.org", "worldbank.org",
    "nhl.com", "fifa.com", "uefa.com", "olympics.com", "oabsp.org.br", "gov.br",
}

REPUTABLE_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "npr.org", "nature.com",
    "science.org", "nationalgeographic.com", "britannica.com",
}

LOW_QUALITY_DOMAINS = {
    "facebook.com", "instagram.com", "pinterest.com", "reddit.com", "tiktok.com", "x.com", "youtube.com",
}

CONCEPTS = {
    "venceu": "win", "vencedor": "win", "vencedora": "win", "ganhou": "win",
    "winner": "win", "wins": "win", "won": "win",
    "superou": "beat", "vence": "beat", "beat": "beat", "beats": "beat", "ahead": "beat",
    "finalista": "finalist", "finalistas": "finalist", "finalist": "finalist", "finalists": "finalist",
    "anuncio": "announce", "anunciou": "announce", "anunciado": "announce", "announced": "announce",
}


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = "web"
    source_quality: str = "general_web"
    relevance_score: int = 0
    excerpt: str = ""


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _tokens(value: str) -> list[str]:
    tokens = [token for token in re.findall(r"[\w'-]+", _fold(value)) if len(token) >= 3 and token not in STOPWORDS]
    return [CONCEPTS.get(token, token) for token in tokens]


def _named_terms(value: str) -> set[str]:
    terms: set[str] = set()
    for token in re.findall(r"\b[A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ'-]{2,}\b|\b[A-Z]{2,}\b", value):
        folded = _fold(token)
        if folded not in STOPWORDS:
            terms.add(folded)
    return terms


def _compact_query(value: str, limit: int = 14) -> str:
    raw = re.findall(r"[\wÀ-ÖØ-öø-ÿ'-]+", value)
    candidates: list[str] = []
    for token in raw:
        folded = _fold(token)
        if len(folded) < 3 or folded in STOPWORDS or folded in {_fold(item) for item in candidates}:
            continue
        candidates.append(token)
    named = [item for item in candidates if item[:1].isupper() or item.isupper() or any(char.isdigit() for char in item)]
    others = sorted((item for item in candidates if item not in named), key=len, reverse=True)
    return " ".join((named + others)[:limit])


def build_queries(claim: str, user_query: str = "", location: str = "", response_date: str = "") -> list[str]:
    # A concise entity-rich query performs much better than sending a full Portuguese paragraph.
    combined = " ".join(part for part in [user_query, claim, response_date] if part).strip()
    queries = [_compact_query(combined), _compact_query(claim)]
    return [query for query in dict.fromkeys(queries) if query]


def _hostname(url: str) -> str:
    return urlparse(url).hostname.lower().removeprefix("www.") if urlparse(url).hostname else ""


def _domain_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def source_quality(url: str) -> str:
    host = _hostname(url)
    if any(_domain_matches(host, domain) for domain in LOW_QUALITY_DOMAINS):
        return "low_quality"
    if (
        any(_domain_matches(host, domain) for domain in AUTHORITATIVE_DOMAINS)
        or host.endswith(".gov")
        or ".gov." in host
        or host.endswith(".mil")
        or host.endswith(".edu")
        or ".edu." in host
    ):
        return "primary_authoritative"
    if any(_domain_matches(host, domain) for domain in REPUTABLE_DOMAINS):
        return "reputable_secondary"
    return "general_web"


def _score_result(item: SearchResult, subject: str, user_intent: str = "") -> tuple[int, bool]:
    subject_terms = set(_tokens(subject))
    named = _named_terms(subject)
    haystack = " ".join([item.title, item.url, item.snippet])
    result_terms = set(_tokens(haystack))
    overlap = subject_terms & result_terms
    named_overlap = named & result_terms
    authority = {"primary_authoritative": 8, "reputable_secondary": 5, "general_web": 1, "low_quality": -8}[item.source_quality]
    direct_concepts = {"win", "beat", "finalist", "announce"}
    direct_overlap = direct_concepts & subject_terms & result_terms
    intent_concepts = direct_concepts & set(_tokens(user_intent)) & result_terms
    title_intent_concepts = direct_concepts & set(_tokens(user_intent)) & set(_tokens(f"{item.title} {item.url}"))
    # The user's question carries the main predicate. A page saying who the finalists were
    # is relevant context, but it must rank below a page that answers who actually won.
    score = (
        len(overlap)
        + (2 * len(named_overlap))
        + (10 * len(direct_overlap))
        + (25 * len(intent_concepts))
        + (50 * len(title_intent_concepts))
        + authority
    )
    # Named entities are a hard topical boundary. "2026" and "liga" cannot turn FIFA into NHL evidence.
    relevant = len(overlap) >= 2 and (not named or bool(named_overlap)) and item.source_quality != "low_quality"
    return score, relevant


def _focused_excerpt(content: str, subject: str, limit: int = 3200) -> str:
    compact = re.sub(r"\s+", " ", content).strip()
    if len(compact) <= limit:
        return compact
    positions = [compact.lower().find(term) for term in sorted(set(_tokens(subject)), key=len, reverse=True)]
    positions = [position for position in positions if position >= 0]
    start = max(0, (min(positions) if positions else 0) - 500)
    return compact[start:start + limit]


def _matches_temporal_date(item: SearchResult, temporal_date: str) -> bool:
    date_parts = [int(part) for part in re.findall(r"\d+", temporal_date)]
    if len(date_parts) < 3:
        return False
    if len(str(date_parts[0])) == 4:
        year, month, day = date_parts[:3]
    else:
        day, month, year = date_parts[:3]
    source_numbers = {int(part) for part in re.findall(r"\d+", " ".join([item.title, item.url, item.snippet]))}
    return {day, month, year}.issubset(source_numbers)


def search_claim(
    claim: str,
    user_query: str = "",
    location: str = "",
    response_date: str = "",
    max_results: int = 5,
    max_queries: int = 2,
    temporal_date: str = "",
) -> dict:
    queries = build_queries(claim, user_query, location, response_date)[:max_queries]
    subject = " ".join([user_query, claim]).strip()
    candidates: list[SearchResult] = []
    errors: list[str] = []
    try:
        from ddgs import DDGS

        with DDGS(timeout=6) as client:
            for query in queries:
                try:
                    items = client.text(
                        query,
                        region="us-en",
                        backend="brave,yahoo,startpage",
                        max_results=max(5, max_results * 2),
                    )
                except Exception as exc:
                    errors.append(f"Search failed for one query: {type(exc).__name__}")
                    continue
                for raw in items:
                    result = SearchResult(
                        title=raw.get("title", ""),
                        url=raw.get("href", raw.get("url", "")),
                        snippet=raw.get("body", raw.get("snippet", "")),
                    )
                    if not result.url or result.url in {existing.url for existing in candidates}:
                        continue
                    result.source_quality = source_quality(result.url)
                    result.relevance_score, relevant = _score_result(result, subject, user_query)
                    if relevant and temporal_date and not _matches_temporal_date(result, temporal_date):
                        relevant = False
                    if relevant:
                        candidates.append(result)

            candidates.sort(
                key=lambda item: (item.source_quality == "primary_authoritative", item.relevance_score),
                reverse=True,
            )

            # Read the best authoritative page. One directly relevant primary source can be sufficient evidence.
            if candidates and candidates[0].source_quality == "primary_authoritative":
                try:
                    page = client.extract(candidates[0].url, fmt="text_plain")
                    candidates[0].excerpt = _focused_excerpt(str(page.get("content", "")), subject)
                except Exception as exc:
                    errors.append(f"Authoritative page extraction failed: {type(exc).__name__}")
    except Exception as exc:
        errors.append(f"Web search unavailable: {type(exc).__name__}")

    results = candidates[:max_results]
    if not results:
        results = [
            SearchResult(
                title=f"Search manually: {query}",
                url=f"https://www.google.com/search?q={quote_plus(query)}",
                snippet="No directly relevant source was retrieved automatically.",
                source="manual_fallback",
            )
            for query in queries
        ]
    return {"queries": queries, "results": [asdict(result) for result in results], "errors": errors}
