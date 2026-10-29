# Shared Contract Corpus — Soft Suave AI Engineering League

**Everyone ingests these five documents. Everyone evaluates against the same 32 cases.**

Until now each of you has been running on a different corpus, which means no two sets of results have been comparable — a 100% pass rate on three one-page PDFs and a 60% pass rate on five full agreements tell us nothing about which system is better. This corpus fixes that.

---

## What's here

The same six documents in **three formats**. Ingest whichever format you like — but
your code must be able to handle all three, because real clients send all three.

```
shared-corpus/
├── contracts/           ← Markdown  (.md)   — source of truth for ground-truth values
├── contracts-docx/      ← Word      (.docx)
├── contracts-pdf/       ← PDF       (.pdf)
│     MSA-2026-014_Northwind_Master_Services_Agreement   ← the anchor document
│     AMD-2026-014-01_Northwind_Amendment_No_1           ← first amendment
│     AMD-2026-014-02_Northwind_Amendment_No_2           ← second amendment (controlling)
│     SCH-2026-014_Northwind_Schedules                   ← Schedules A, B, B-2, C, D (TABLES)
│     MSA-2026-022_Vertex_Master_Services_Agreement      ← second counterparty
│     NDA-2026-007_Mutual_Non_Disclosure_Agreement       ← third party, different doc type
├── eval/
│     golden_set.json                                    ← 32 cases with ground truth
└── loaders/
      document_loader.py                                 ← reference multi-format loader
      verify_corpus.py                                   ← proves your loader reads all 3 the same
```

All three formats are verified to yield the same facts and the same metadata —
`verify_corpus.py` checks 20 ground-truth values, including every table value,
across all three. It passes on the files as shipped.

---

## The rules

1. **Ingest all six documents.** Not a subset. Several evaluation cases depend on documents being present together.
2. **Your pipeline must support `.md`, `.docx` and `.pdf`.** Pick one format to ingest for your own runs, but the loader has to handle all three — see below.
3. **Do not edit the contracts.** Ground-truth answers are keyed to exact clause values.
4. **Do not edit `golden_set.json`.** If you think a value is wrong, raise it — don't fix it locally. A changed eval set voids every comparison we make.
5. **Attach the metadata below to every chunk.** Several cases cannot be passed without it.
6. **Report results against the case IDs** (`GS-001` … `GS-032`) so numbers line up across the team.

---

## Handling three formats

```bash
pip install pdfplumber python-docx
```

`loaders/document_loader.py` is a working reference implementation. Read it, then
adapt it — don't just import it. It exists to enforce three things that are easy
to get wrong and expensive to debug:

**1. Tables must survive as text.** Schedule B (fees and service levels),
Schedule B-2 (breach notification deadlines) and Schedule C (holiday calendar)
are tables. A loader that silently drops them makes GS-011, GS-013, GS-015,
GS-018 and GS-019 unanswerable — and you will spend a day blaming your chunker
for a loader bug. The reference loader flags this explicitly as a warning.

**2. A table row must carry its own header.** Each row is emitted as
`Date: 20 October 2026 | Holiday: Deepavali` rather than a bare `20 October 2026 | Deepavali`,
so that a chunk containing one row still means something on its own. This is the
same requirement the Week 3 brief made about never separating a table row from
its header.

**3. Metadata comes from the document, not the filename.** Every document opens
with a header block carrying Agreement No., Counterparty, Effective Date and
Status. Parse it.

Then check your work:

```bash
cd loaders && python verify_corpus.py
```

It loads every document in all three formats and asserts that 20 specific
ground-truth values — and the extracted metadata — agree across them. Exit code
0 means your three formats are interchangeable. Non-zero means one of them is
losing content, and that is a bug to fix **before** you trust any eval number.

Two known, acceptable differences: PDF reports a slightly higher table count
(a table spanning a page break is found twice) and character counts vary by
about 1% (whitespace). Content parity is what matters.

---

## Required chunk metadata

Every chunk you index must carry these five fields. A chunk missing `source_doc` or `counterparty` is a failed ingest.

| Field | Values | Why it matters |
|---|---|---|
| `source_doc` | `MSA-2026-014`, `AMD-2026-014-01`, `AMD-2026-014-02`, `SCH-2026-014`, `MSA-2026-022`, `NDA-2026-007` | Citation resolution |
| `counterparty` | `Northwind Logistics`, `Vertex Retail`, `Halcyon Analytics` | **Required for GS-006, 024, 025, 026** — the same section number exists in two agreements with different values |
| `effective_date` | `2026-01-14`, `2026-04-01`, `2026-08-01`, `2026-03-03`, `2026-05-22` | **Required for the amendment chain** — later date wins |
| `doc_type` | `master_agreement`, `amendment`, `schedule`, `nda` | Lets you prefer amendments over originals |
| `clause_ref` | e.g. `Section 8.3`, `Schedule B-2 Part 2` | Citation must resolve to a real clause |

Suggested: also keep a stable `chunk_id` so citations are checkable.

---

## What the corpus is designed to break

This isn't a neutral set of documents. Each one is here to make a specific failure mode possible.

### 1. The amendment chain — supersession
`MSA-2026-014` → `Amendment No. 1` → `Amendment No. 2`. Three values move twice:

| Provision | Original | Amendment 1 | Amendment 2 | **Correct answer** |
|---|---|---|---|---|
| Termination notice (§7.3) | 60 days | 30 days | 15 Business Days | **15 Business Days** |
| Payment terms (§3.3) | 30 days | 45 days | *expressly unchanged* | **45 days** |
| Cure Period (§1.4) | 30 days | 45 days | — | **45 days** |
| Liability cap (§8.3) | USD 2,000,000 | — | greater of USD 5m or 12-month fees | **USD 5m / 12-month fees** |
| Confidentiality survival (§5.3) | 5 years | — | 7 years | **7 years** |

A system that answers "60 days" or "USD 2,000,000" is confidently quoting a dead clause. That is the single most dangerous failure in contract review, and it is what GS-005, 007, 008, 009, 012 test.

### 2. Two counterparties, same section numbers — retrieval disambiguation
`MSA-2026-014` (Northwind) and `MSA-2026-022` (Vertex) use **identical section numbering** with **different values**:

| | Northwind | Vertex |
|---|---|---|
| §8.3 liability cap | USD 5,000,000 (as amended) | **USD 500,000** |
| §3.3 payment terms | 45 days (as amended) | **60 days** |
| §3.4 late interest | 1.5%/month | **1.0%/month** |
| §1.4 Cure Period | 45 days (as amended) | **20 days** |
| §15 dispute resolution | Chennai courts, India | **SIAC arbitration, Singapore** |
| §3.6 fee increase cap | 5% pa | **3% pa** |

Ask "what is the cap in Section 8.3" without a counterparty filter and dense retrieval will happily return the wrong agreement. GS-006, 024, 025, 026 are built on this.

### 3. Defined terms that point elsewhere — multi-hop
- `"Business Day"` (§1.2) → **Schedule C** holiday calendar. GS-010, GS-011.
- `"Service Level"` (§1.8) → **Schedule B Part 2**. `"Service Failure"` (§1.7) → Service Level. `"Qualifying Event"` (§1.6) → three Service Failures. That's a three-hop chain: GS-014.
- §7.6 (added by Amendment 2) → **Schedule B-2 Part 2** breach deadlines → **Cure Period** (as amended). Three hops across three documents: GS-013.

These are the cases that tell you whether an agent earns its cost over a fixed workflow.

### 4. Deliberate gaps — refusal testing
Four cases have no answer in the corpus (GS-029 … GS-032):
- There is no Apex Industries agreement.
- The Vertex agreement has no holiday calendar schedule — and a system that borrows Northwind's Schedule C has hallucinated.
- There is no Service SVC-05.
- The Vertex agreement has no amendments — attributing Northwind's amendments to it is a failure.

A system that scores well on the first 28 and invents answers to these is not safe to put in front of a lawyer.

### 5. A known hallucination trap
GS-023 asks about the confidentiality standard of care. The answer is **"a reasonable degree of care"** (§5.1). Models frequently upgrade this to a "fiduciary" or "utmost" standard because it sounds safer. It isn't — it's an ungrounded change to a party's legal exposure, and it counts as a hallucination, not a conservative reading.

---

## Suggested evaluation report format

So results line up, please report in this shape:

```
Overall pass rate:        __/32

By class:
  direct_lookup                __/8
  amendment_supersession       __/7
  counterparty_disambiguation  __/4
  out_of_scope (refusal)       __/4
  defined_term_chase           __/3
  multi_hop_dependent          __/2
  computation                  __/2
  version_comparison           __/1
  cross_document               __/1

Failure breakdown:
  fail_wrong_version           __   (quoted a superseded clause)
  fail_wrong_counterparty      __   (right section, wrong agreement)
  fail_hallucination           __   (value not in the cited source)
  fail_false_refusal           __   (refused something answerable)
```

The **out_of_scope** and **amendment_supersession** rows are the ones that matter most. A high overall score with failures in those two is worse than a lower score with them clean.

---

## Converting to other formats

If you need a format not shipped here, convert from the Markdown and re-run `verify_corpus.py` — **the Markdown is the source of truth** for ground-truth answers. If a conversion drops a table (Schedules B, B-2 and C are tables), several cases become unanswerable and that is a conversion bug, not a retrieval one.

---

## A note on what this changes

Two things stop being excuses after this:

- **"My corpus is small"** — these are full-length agreements with schedules, amendment chains and cross-references. If a case fails now, it fails for a real reason.
- **"My numbers aren't comparable to anyone else's"** — they are now. Same documents, same questions, same ground truth.

Which also means: if your pass rate drops when you move to this corpus, that is the correct and useful outcome. Report it. A number that goes down on harder data is worth more than a number that was never tested.
