from __future__ import annotations

import html
import re


_SECTION_BODY_START = "A|An|The|Assessors|Assign|Available|Evidence|Factuality|Human|Use|When"
_SECTION_RE = re.compile(
    rf"(?<!\S)(\d+\.\d+\s+[A-Z][A-Za-z /&-]{{2,55}}?)"
    rf"(?=\s+(?:{_SECTION_BODY_START})\b)"
)
_LIST_ITEM_RE = re.compile(r"(?<!\S)(?:-|(\d+)\.)\s+([^:]{1,75}):\s*")


def _render_body(text: str) -> str:
    """Turn flattened PDF prose into readable paragraphs and definition lists."""
    text = " ".join(text.split()).strip()
    if not text:
        return ""

    matches = list(_LIST_ITEM_RE.finditer(text))
    if not matches:
        return f'<p class="guideline-paragraph">{html.escape(text)}</p>'

    intro = text[: matches[0].start()].strip()
    parts = []
    if intro:
        parts.append(f'<p class="guideline-paragraph">{html.escape(intro)}</p>')

    list_class = "guideline-list numbered" if matches[0].group(1) else "guideline-list"
    items = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        label = html.escape(match.group(2).strip())
        description = html.escape(text[match.end() : end].strip())
        items.append(
            '<li><span class="guideline-label">'
            f'{label}</span><span class="guideline-description">{description}</span></li>'
        )
    parts.append(f'<ol class="{list_class}">{"".join(items)}</ol>')
    return "".join(parts)


def format_guideline_citation(citation: dict) -> str:
    """Render a retrieved guideline citation as a semantic, light-mode card."""
    source = html.escape(str(citation.get("source") or "Diretriz"))
    page = html.escape(str(citation.get("page") or "—"))
    primary_section = str(citation.get("section") or "Trecho consultado").strip()
    raw_text = " ".join(str(citation.get("text") or "").split()).strip()

    if raw_text.casefold().startswith(primary_section.casefold()):
        raw_text = raw_text[len(primary_section) :].strip()

    section_matches = list(_SECTION_RE.finditer(raw_text))
    sections: list[tuple[str, str]] = []
    first_end = section_matches[0].start() if section_matches else len(raw_text)
    sections.append((primary_section, raw_text[:first_end].strip()))
    for index, match in enumerate(section_matches):
        end = section_matches[index + 1].start() if index + 1 < len(section_matches) else len(raw_text)
        sections.append((match.group(1).strip(), raw_text[match.end() : end].strip()))

    rendered_sections = []
    for title, body in sections:
        if not title and not body:
            continue
        rendered_sections.append(
            '<section class="guideline-section">'
            f'<h4>{html.escape(title)}</h4>{_render_body(body)}'
            "</section>"
        )

    return (
        '<article class="guideline-card">'
        '<div class="guideline-meta">'
        f'<span class="guideline-source">{source}</span><span>Página {page}</span>'
        "</div>"
        f'{"".join(rendered_sections)}'
        "</article>"
    )
