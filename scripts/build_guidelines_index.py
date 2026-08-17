from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "data" / "index" / "guidelines.json"

PRIVATE_GUIDE = Path(os.environ.get(
    "FACTUALITY_GUIDELINES_PATH",
    ROOT / "knowledge_private" / "factuality_guidelines.pdf",
))

# Public executions always have the synthetic guide. A private guide can be
# supplied locally through FACTUALITY_GUIDELINES_PATH and is never packaged.
SOURCES = [
    ("factuality_private", "factuality", PRIVATE_GUIDE),
    ("factuality_sample", "factuality", ROOT / "data" / "sample_factuality_guide.pdf"),
]

HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*\s+[^\n]+|(?:PART|Part)\s+[^\n]+)$")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def section_for(page_text: str, previous: str) -> str:
    for line in page_text.splitlines():
        line = normalize(line)
        if HEADING.match(line) and len(line) < 180:
            return line
    return previous


def build() -> dict:
    chunks = []
    seen = set()
    found_any = False
    for source_name, task_type, path in SOURCES:
        if not path.exists():
            continue
        found_any = True
        reader = PdfReader(str(path))
        section = "Overview"
        for page_number, page in enumerate(reader.pages, start=1):
            raw = page.extract_text() or ""
            section = section_for(raw, section)
            text = normalize(raw)
            if not text:
                continue
            words = re.findall(r"[\w-]{4,}", text.lower())
            key = (path.name, page_number, task_type)
            if key in seen:
                continue
            seen.add(key)
            chunks.append({
                "id": f"{source_name}-{task_type}-{page_number}",
                "source": path.name,
                "source_path": str(path.relative_to(ROOT)),
                "task_type": task_type,
                "page": page_number,
                "section": section,
                "text": text,
                "keywords": sorted(set(words)),
            })
    return {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chunks": chunks,
    }


if __name__ == "__main__":
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(build(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Indexed guidelines: {INDEX_PATH}")
