"""
Format parity check for the shared contract corpus.

Proves that .md, .docx and .pdf all yield the same contract facts, so your
retrieval results do not depend on which format you ingested.

Run it after ingesting, and run it again if you change your loader:

    python verify_corpus.py

Exit code 0 = all three formats agree. Non-zero = one of them is losing content,
and that is a loader bug you need to fix before you trust any eval number.
"""

from __future__ import annotations

import sys
from pathlib import Path

from document_loader import load_document

ROOT = Path(__file__).resolve().parent.parent
FORMATS = {"md": ROOT / "contracts", "docx": ROOT / "contracts-docx", "pdf": ROOT / "contracts-pdf"}

# (document stem, needle, why it matters)
CHECKS: list[tuple[str, str, str]] = [
    # --- plain clause text
    ("MSA-2026-014_Northwind_Master_Services_Agreement", "1.5%", "GS-001 late payment rate"),
    ("MSA-2026-014_Northwind_Master_Services_Agreement", "Chennai", "GS-002 jurisdiction"),
    ("MSA-2026-014_Northwind_Master_Services_Agreement", "72", "GS-004 breach notification"),
    ("MSA-2026-014_Northwind_Master_Services_Agreement", "13 January 2028", "GS-020 expiry date"),
    ("MSA-2026-014_Northwind_Master_Services_Agreement", "reasonable degree of care", "GS-023 standard of care"),
    # --- amendment chain
    ("AMD-2026-014-01_Northwind_Amendment_No_1", "forty-five (45) days", "GS-008 payment terms"),
    ("AMD-2026-014-02_Northwind_Amendment_No_2", "fifteen (15) Business Days", "GS-007 termination notice"),
    ("AMD-2026-014-02_Northwind_Amendment_No_2", "5,000,000", "GS-005 liability cap"),
    ("AMD-2026-014-02_Northwind_Amendment_No_2", "seven (7) years", "GS-009 confidentiality survival"),
    # --- counterparty disambiguation
    ("MSA-2026-022_Vertex_Master_Services_Agreement", "500,000", "GS-006 Vertex cap"),
    ("MSA-2026-022_Vertex_Master_Services_Agreement", "SIAC", "GS-025 Vertex arbitration"),
    ("MSA-2026-022_Vertex_Master_Services_Agreement", "twenty (20) days", "GS-026 Vertex cure period"),
    # --- TABLES: the content most likely to be lost in conversion
    ("SCH-2026-014_Northwind_Schedules", "Deepavali", "GS-011 holiday calendar (Schedule C table)"),
    ("SCH-2026-014_Northwind_Schedules", "20 October 2026", "GS-011 holiday date (Schedule C table)"),
    ("SCH-2026-014_Northwind_Schedules", "15 Business Days", "GS-013 breach deadline (Schedule B-2 table)"),
    ("SCH-2026-014_Northwind_Schedules", "81,100", "GS-018 total monthly fee (Schedule B table)"),
    ("SCH-2026-014_Northwind_Schedules", "42,000", "GS-019 SVC-01 fee (Schedule B table)"),
    ("SCH-2026-014_Northwind_Schedules", "99.9%", "GS-015 availability target (Schedule B table)"),
    # --- NDA
    ("NDA-2026-007_Mutual_Non_Disclosure_Agreement", "50,000", "GS-028 NDA liability cap"),
    ("NDA-2026-007_Mutual_Non_Disclosure_Agreement", "England and Wales", "GS-027 NDA governing law"),
]

EXT = {"md": ".md", "docx": ".docx", "pdf": ".pdf"}


def main() -> int:
    cache: dict[tuple[str, str], object] = {}
    missing_fmt = [f for f, d in FORMATS.items() if not d.is_dir()]
    if missing_fmt:
        print(f"SKIP: format directories not present: {', '.join(missing_fmt)}")
        return 0

    failures: list[str] = []
    print(f"{'CHECK':<52} {'MD':>4} {'DOCX':>6} {'PDF':>5}")
    print("-" * 70)

    for stem, needle, why in CHECKS:
        row = {}
        for fmt, folder in FORMATS.items():
            key = (fmt, stem)
            if key not in cache:
                cache[key] = load_document(folder / f"{stem}{EXT[fmt]}")
            doc = cache[key]
            # normalise whitespace for comparison; conversion can alter spacing
            hay = " ".join(doc.text.split()).lower()
            row[fmt] = " ".join(needle.split()).lower() in hay
        mark = {True: "OK", False: "MISS"}
        print(f"{why:<52} {mark[row['md']]:>4} {mark[row['docx']]:>6} {mark[row['pdf']]:>5}")
        for fmt, ok in row.items():
            if not ok:
                failures.append(f"{stem} [{fmt}] missing {needle!r} ({why})")

    print("-" * 70)

    # metadata parity
    print("\nMETADATA PARITY")
    meta_fail = 0
    stems = sorted({s for s, _, _ in CHECKS})
    for stem in stems:
        metas = {}
        for fmt, folder in FORMATS.items():
            doc = cache.get((fmt, stem)) or load_document(folder / f"{stem}{EXT[fmt]}")
            m = doc.metadata
            metas[fmt] = (m["source_doc"], m["counterparty"], m["effective_date"], m["doc_type"])
        agree = len(set(metas.values())) == 1
        print(f"  {'OK ' if agree else 'DIFF'}  {stem[:46]:<46} {metas['md'][1]}, {metas['md'][2]}")
        if not agree:
            meta_fail += 1
            for fmt, v in metas.items():
                print(f"          {fmt}: {v}")

    # table counts
    print("\nTABLE EXTRACTION")
    for stem in stems:
        counts = {}
        for fmt in FORMATS:
            doc = cache.get((fmt, stem))
            counts[fmt] = doc.tables_found if doc else 0
        flag = "" if counts["md"] == 0 or all(c > 0 for c in counts.values()) else "   <-- TABLES LOST"
        print(f"  {stem[:46]:<46} md={counts['md']:<3} docx={counts['docx']:<3} pdf={counts['pdf']:<3}{flag}")

    print()
    if failures or meta_fail:
        print(f"FAILED: {len(failures)} content mismatch(es), {meta_fail} metadata mismatch(es)")
        for f in failures[:20]:
            print("  -", f)
        return 1
    print(f"PASSED: all {len(CHECKS)} facts present in all three formats; metadata agrees.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
