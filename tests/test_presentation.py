from src.presentation import format_guideline_citation


def test_rating_scale_is_rendered_as_cascade() -> None:
    citation = {
        "source": "sample_factuality_guide.pdf",
        "page": 3,
        "section": "4.0 Factuality Rating Scale",
        "text": (
            "4.0 Factuality Rating Scale Assign one of the ratings: "
            "- Accurate: Confirmed by evidence. "
            "- Inaccurate: Contradicted by evidence."
        ),
    }
    rendered = format_guideline_citation(citation)
    assert rendered.count("4.0 Factuality Rating Scale") == 1
    assert '<ol class="guideline-list">' in rendered
    assert '<span class="guideline-label">Accurate</span>' in rendered
    assert "Confirmed by evidence." in rendered
    assert not rendered.endswith("...")


def test_embedded_pdf_section_gets_its_own_heading() -> None:
    citation = {
        "source": "guide.pdf",
        "page": 1,
        "section": "1.0 Overview of Factuality Evaluation",
        "text": (
            "1.0 Overview of Factuality Evaluation Factuality assessment verifies claims. "
            "2.0 Identifying Claims A factual claim asserts a verifiable fact."
        ),
    }
    rendered = format_guideline_citation(citation)
    assert "<h4>1.0 Overview of Factuality Evaluation</h4>" in rendered
    assert "<h4>2.0 Identifying Claims</h4>" in rendered
    assert rendered.count('class="guideline-section"') == 2


def test_guideline_content_is_html_escaped() -> None:
    rendered = format_guideline_citation(
        {"source": "<guide>", "page": 1, "section": "Rules", "text": "<script>alert(1)</script>"}
    )
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
