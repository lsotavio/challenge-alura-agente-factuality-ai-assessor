"""Script to generate a synthetic Factuality & Severity Evaluation Guideline PDF for demonstration and test runs."""
from pathlib import Path


def create_minimal_pdf(output_path: Path):
    # Standard multi-page PDF with clear sections and headings for Factuality Evaluation
    content_pages = [
        # Page 1: Overview and Identifying Claims
        (
            "1.0 Overview of Factuality Evaluation\n\n"
            "Factuality assessment is the process of verifying whether verifiable factual claims "
            "contained in AI model responses are true, supported by reliable evidence, or inaccurate.\n\n"
            "Assessors must evaluate each checkable claim against high-quality, reputable external sources. "
            "Evaluations must distinguish verifiable claims from subjective opinions, pleasantries, and advice.\n\n"
            "2.0 Identifying Claims\n\n"
            "A factual claim is a statement that asserts a verifiable fact about the real world, entities, dates, "
            "statistics, scientific principles, historical events, or geographical data.\n\n"
            "- Checkable claims: 'The Denver Nuggets won the 2023 NBA Championship.'\n"
            "- Subjective / non-checkable: 'The game was exciting to watch.'\n"
            "- Ambiguous context: Assess claims in relation to user query and location."
        ),
        # Page 2: Researching Claims & Source Quality Hierarchy
        (
            "3.0 Researching Claims and Evidence\n\n"
            "Assessors must search for reputable external evidence before making a rating decision.\n\n"
            "Hierarchy of Source Quality:\n"
            "1. Primary / Authoritative Sources: Official government portals (.gov, .gov.br), international organizations (WHO, UN, NASA, NOAA), official sports leagues (FIFA, NHL, NBA), and academic peer-reviewed institutions.\n"
            "2. Reputable Secondary Sources: Established news agencies (Reuters, AP News, BBC), major encyclopedias, and recognized educational platforms.\n"
            "3. Low Quality / Unverifiable: Social media posts, user forums, anonymous blogs, and uncorroborated marketing sites.\n\n"
            "Evidence must directly confirm or refute the specific entity and predicate in the claim."
        ),
        # Page 3: Factuality Rating Scale
        (
            "4.0 Factuality Rating Scale\n\n"
            "Assign one of the six standard ratings:\n\n"
            "- Accurate: The claim is confirmed by reputable and authoritative evidence.\n"
            "- Inaccurate: The claim is contradicted by reputable and authoritative evidence.\n"
            "- Unsupported: The claim asserts a verifiable fact, but thorough search reveals no reliable corroboration.\n"
            "- Disputed: Authoritative sources directly disagree on the fact with no prevailing consensus.\n"
            "- Can't confidently assess: Available evidence is inaccessible, contradictory without resolution, or insufficient.\n"
            "- No claims present: The sentence contains solely opinions, recommendations, greetings, or non-factual text."
        ),
        # Page 4: Human Review and Oversight
        (
            "5.0 Human Review and Oversight\n\n"
            "The AI agent acts strictly as an assistant providing evidence and suggested ratings. "
            "Human assessors maintain final authority and oversight for all submitted ratings."
        ),
    ]

    # Let's generate a valid PDF with cross-reference table and stream objects
    objects = []
    
    # 1: Catalog
    # 2: Pages
    # 3..: Page objects, Font, and Content streams
    page_count = len(content_pages)
    
    font_obj_id = 3 + page_count * 2
    
    page_obj_ids = []
    content_obj_ids = []
    
    current_id = 3
    for _ in range(page_count):
        page_obj_ids.append(current_id)
        content_obj_ids.append(current_id + 1)
        current_id += 2

    # Build objects
    # Obj 1: Catalog
    obj_1 = "<< /Type /Catalog /Pages 2 0 R >>"
    
    # Obj 2: Pages
    kids_str = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    obj_2 = f"<< /Type /Pages /Kids [ {kids_str} ] /Count {page_count} >>"
    
    objs = {1: obj_1, 2: obj_2}
    
    for idx in range(page_count):
        pid = page_obj_ids[idx]
        cid = content_obj_ids[idx]
        page_text = content_pages[idx]
        
        # Format text for PDF text stream
        lines = page_text.split("\n")
        stream_lines = ["BT", "/F1 11 Tf", "50 750 Td", "14 TL"]
        for line in lines:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            if escaped.startswith("1.0") or escaped.startswith("2.0") or escaped.startswith("3.0") or escaped.startswith("4.0") or escaped.startswith("5.0") or escaped.startswith("6.0"):
                stream_lines.append(f"({escaped}) Tj T*")
            else:
                stream_lines.append(f"({escaped}) Tj T*")
        stream_lines.append("ET")
        stream_content = "\n".join(stream_lines).encode("latin1", errors="replace")
        
        objs[pid] = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {cid} 0 R /Resources << /Font << /F1 {font_obj_id} 0 R >> >> >>"
        objs[cid] = f"<< /Length {len(stream_content)} >>\nstream\n".encode("latin1") + stream_content + b"\nendstream"
        
    objs[font_obj_id] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    
    # Write PDF file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        f.write(b"%PDF-1.4\n")
        offsets = {}
        for oid in range(1, font_obj_id + 1):
            offsets[oid] = f.tell()
            f.write(f"{oid} 0 obj\n".encode("latin1"))
            val = objs[oid]
            if isinstance(val, str):
                f.write(val.encode("latin1"))
            else:
                f.write(val)
            f.write(b"\nendobj\n")
            
        xref_offset = f.tell()
        f.write(f"xref\n0 {font_obj_id + 1}\n".encode("latin1"))
        f.write(b"0000000000 65535 f \n")
        for oid in range(1, font_obj_id + 1):
            f.write(f"{offsets[oid]:010d} 00000 n \n".encode("latin1"))
        f.write(f"trailer\n<< /Size {font_obj_id + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin1"))


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "data" / "sample_factuality_guide.pdf"
    create_minimal_pdf(out)
    print(f"Generated {out}")
