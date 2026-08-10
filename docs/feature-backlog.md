# Feature backlog — Legal Document RAG Assistant

Status of user-visible features. Update this file in the same commit that ships
or changes a feature.

| Feature | Status | Notes |
|---|---|---|
| CLI: ingest / ask / chat (`main.py`) | Shipped | One-shot questions, interactive loop, JSON output |
| Grounded RAG pipeline (retrieve → re-rank → generate) | Shipped | Local bi-encoder + Chroma + cross-encoder; extractive fallback when no LLM endpoint |
| Input guardrails (injection / drafting refusal) | Shipped | Fixed safe responses, `out_of_scope=true` |
| Streamlit web UI (`ui.py`) | Shipped 2026-08-10 | Question box, backend + document-type selectors, sources/reasoning display, re-ingest button |
