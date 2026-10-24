"""
Reference multi-format document loader for the Soft Suave AI League shared corpus.

Handles .md, .docx and .pdf and returns the SAME text for all three, so your
retrieval results do not depend on which format you happened to ingest.

Adapt it into your own pipeline — do not just import it blindly. The important
parts are the three rules at the bottom of this docstring, not this exact code.

    pip install pdfplumber python-docx

Three rules this loader exists to enforce:

1. TABLES MUST SURVIVE AS TEXT. Schedule B-2 (breach notification deadlines) and
   Schedule C (holiday calendar) are tables. A loader that drops them silently
   makes GS-011, GS-013 and GS-019 unanswerable, and you will spend a day blaming
   your chunker for a loader bug.

2. A TABLE ROW MUST NOT BE SPLIT FROM ITS HEADER. Each row is emitted with its
   column names inline ("Date: 20 October 2026 | Holiday: Deepavali") so that a
   chunk containing one row still carries the meaning of that row.

3. METADATA COMES FROM THE DOCUMENT, NOT THE FILENAME. The header block at the
   top of every contract carries Agreement No., Counterparty, Effective Date and
   Status. Parse it. Several golden-set cases cannot pass without `counterparty`
   and `effective_date` on every chunk.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SUPPORTED = {".md", ".markdown", ".docx", ".pdf"}

# Counterparty -> canonical label used in chunk metadata.
_COUNTERPARTIES = {
    "northwind": "Northwind Logistics",
    "vertex": "Vertex Retail",
    "halcyon": "Halcyon Analytics",
}

_DOC_TYPES = [
    (r"amendment\s+no", "amendment"),
    (r"schedules?\s+to", "schedule"),
    (r"non-disclosure", "nda"),
    (r"master\s+services\s+agreement", "master_agreement"),
]


@dataclass
class LoadedDocument:
    text: str
    metadata: dict[str, Any]
    source_path: str
    source_format: str
    tables_found: int = 0
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# format readers — each returns (plain_text, table_count)
# --------------------------------------------------------------------------

def _read_markdown(path: Path) -> tuple[str, int]:
    raw = path.read_text(encoding="utf-8")
    out, tables, lines, i = [], 0, raw.split("\n"), 0

    def is_sep(line_text: str) -> bool:
        s = line_text.strip()
        return bool(s) and set(s) <= set("|-: ") and "-" in s and "|" in s

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("|") and i + 1 < len(lines) and is_sep(lines[i + 1]):
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append(_flatten_table(header, rows))
            tables += 1
            continue
        # strip markdown emphasis so all three formats yield the same tokens
        out.append(re.sub(r"[*_`]{1,2}", "", line))
        i += 1

    return "\n".join(out), tables


def _read_docx(path: Path) -> tuple[str, int]:
    import docx  # python-docx

    document = docx.Document(str(path))
    body = document.element.body
    parts, tables = [], 0
    # Walk paragraphs and tables in true document order.
    p_iter = iter(document.paragraphs)
    t_iter = iter(document.tables)
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            with contextlib.suppress(StopIteration):
                parts.append(next(p_iter).text)
        elif tag == "tbl":
            try:
                tbl = next(t_iter)
            except StopIteration:
                continue
            rows = [[c.text.strip() for c in r.cells] for r in tbl.rows]
            if rows:
                parts.append(_flatten_table(rows[0], rows[1:]))
                tables += 1
    return "\n".join(parts), tables


def _read_pdf(path: Path) -> tuple[str, int]:
    import pdfplumber

    parts, tables = [], 0
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            extracted = page.extract_tables() or []
            # Narrative text FIRST, then tables — this keeps the document title
            # as the first line, which metadata extraction depends on.
            body = page
            if extracted:
                for tbl_obj in page.find_tables():
                    # drop table regions so rows are not emitted twice
                    body = body.outside_bbox(tbl_obj.bbox)
            parts.append(body.extract_text() or "")
            for tbl in extracted:
                rows = [[(c or "").strip().replace("\n", " ") for c in r] for r in tbl if r]
                if len(rows) >= 2:
                    parts.append(_flatten_table(rows[0], rows[1:]))
                    tables += 1
    # NOTE: a table spanning a page break is reported as two tables here, so the
    # PDF table count can legitimately exceed the Markdown count. Content parity
    # is what matters — see verify_corpus.py.
    return "\n".join(parts), tables


def _flatten_table(header: list[str], rows: list[list[str]]) -> str:
    """Emit each row carrying its own column names, so a chunk containing one
    row still means something on its own."""
    out = ["[TABLE] " + " | ".join(h for h in header if h)]
    for row in rows:
        pairs = [
            f"{header[i]}: {cell}" if i < len(header) and header[i] else cell
            for i, cell in enumerate(row)
            if cell
        ]
        if pairs:
            out.append("  " + " | ".join(pairs))
    return "\n".join(out)


# --------------------------------------------------------------------------
# metadata
# --------------------------------------------------------------------------

# Labels that appear in the header block of every corpus document. Used both to
# find a field and to know where that field's value ends — without the second
# part, a value swallows the rest of the header when the block is one paragraph.
_HEADER_LABELS = [
    r"Agreement No\.", r"Amendment No\.", r"Document No\.", r"Amends",
    r"Forms part of", r"Counterparty", r"Provider", r"Effective Date",
    r"Document Version", r"Status",
]
_STOP = "|".join(_HEADER_LABELS)


def extract_metadata(text: str, path: Path) -> dict[str, Any]:
    head = text[:2000]
    # Document title = first real line of prose. Skip flattened table rows, which
    # can lead the text when a PDF page opens with a table.
    title = ""
    for ln in text.split("\n"):
        s = ln.strip()
        if not s or s.startswith("[TABLE]") or ln.startswith("  "):
            continue
        title = s.lstrip("# ").strip()
        break

    def grab(label: str) -> str | None:
        """Capture a header field, stopping at the next known label so the value
        does not run on when the whole block is a single paragraph."""
        m = re.search(
            rf"(?:{label})\s*:?\s*\**\s*(.+?)(?=\s*(?:{_STOP})\s*:|\n|$)",
            head, re.I | re.S,
        )
        if not m or m.group(1) is None:
            return None
        return m.group(1).strip().strip("*").strip() or None

    # --- source_doc: the identifier in the field block, never the title ------
    source_doc = None
    for label in (r"Agreement No\.", r"Amendment No\.", r"Document No\."):
        val = grab(label)
        # a real identifier looks like MSA-2026-014 / AMD-2026-014-01 / SCH-2026-014
        if val and (m := re.search(r"\b([A-Z]{2,4}-\d{4}-\d{3}(?:-\d{2})?)\b", val)):
            source_doc = m.group(1)
            break
    if not source_doc:
        m = re.search(r"\b([A-Z]{2,4}-\d{4}-\d{3}(?:-\d{2})?)\b", head)
        source_doc = m.group(1) if m else path.stem.split("_")[0]

    # --- counterparty: ONLY from the Counterparty field ---------------------
    # Never scan the whole header: documents cross-reference each other by name
    # (the Vertex agreement mentions Northwind), and a loose scan picks the
    # wrong party — which silently breaks every counterparty-filtered query.
    counterparty = None
    if cp := grab("Counterparty"):
        for key, label in _COUNTERPARTIES.items():
            if key in cp.lower():
                counterparty = label
                break

    # --- effective_date -----------------------------------------------------
    effective_date = None
    if (raw_date := grab("Effective Date")) and (
        dm := re.match(r"(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2})", raw_date.strip())
    ):
        for fmt in ("%d %B %Y", "%d %b %Y", "%Y-%m-%d"):
            try:
                effective_date = datetime.strptime(dm.group(1), fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue

    # --- doc_type: from the TITLE, not the body -----------------------------
    # The master agreement's header mentions "Amendment No. 1 and No. 2" as
    # cross-references; matching on the body would label the original an amendment.
    doc_type = "unknown"
    for pattern, label in _DOC_TYPES:
        if re.search(pattern, title, re.I):
            doc_type = label
            break

    status = grab("Status") or "unknown"

    return {
        "source_doc": source_doc,
        "counterparty": counterparty,
        "effective_date": effective_date,
        "doc_type": doc_type,
        "status": status,
        "is_controlling": "CURRENT" in status.upper() or "CONTROLLING" in status.upper(),
    }


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------

def load_document(path: str | Path) -> LoadedDocument:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"Unsupported format {suffix!r}. Supported: {sorted(SUPPORTED)}")

    reader = {
        ".md": _read_markdown, ".markdown": _read_markdown,
        ".docx": _read_docx, ".pdf": _read_pdf,
    }[suffix]
    text, tables = reader(path)

    # Normalise whitespace so the same contract in three formats chunks identically.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    meta = extract_metadata(text, path)
    warnings: list[str] = []
    # Only the Schedules document actually contains tables; the agreements merely
    # cross-reference it. Warn when the table-bearing document yields no tables,
    # which is the single most common and most silent ingestion bug.
    if tables == 0 and meta.get("doc_type") == "schedule":
        warnings.append(
            "This document contains tables (Schedules B, B-2, C) but none were "
            "extracted. GS-011, GS-013, GS-018 and GS-019 will be unanswerable. "
            "This is a loader bug, not a retrieval bug."
        )
    for required in ("source_doc", "counterparty", "effective_date"):
        if not meta.get(required):
            warnings.append(f"Missing required metadata field: {required}")

    return LoadedDocument(
        text=text, metadata=meta, source_path=str(path),
        source_format=suffix.lstrip("."), tables_found=tables, warnings=warnings,
    )


def load_directory(directory: str | Path) -> list[LoadedDocument]:
    directory = Path(directory)
    docs = []
    for p in sorted(directory.iterdir()):
        if p.suffix.lower() in SUPPORTED:
            docs.append(load_document(p))
    return docs


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "../contracts"
    for d in load_directory(target):
        print(f"\n{d.metadata['source_doc']}  [{d.source_format}]")
        print(f"  counterparty   : {d.metadata['counterparty']}")
        print(f"  effective_date : {d.metadata['effective_date']}")
        print(f"  doc_type       : {d.metadata['doc_type']}")
        print(f"  controlling    : {d.metadata['is_controlling']}")
        print(f"  chars / tables : {len(d.text):,} / {d.tables_found}")
        for w in d.warnings:
            print(f"  WARNING        : {w}")
