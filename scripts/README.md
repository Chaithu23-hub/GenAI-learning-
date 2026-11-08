# Repository tools

Run these commands from the repository root using the project virtual environment.

`ci/` contains maintained GitHub Actions gates and local validation helpers. Output is summarized to avoid exposing document text or credentials:

```powershell
.\.venv\Scripts\python.exe scripts/ci/quality_checks.py
.\.venv\Scripts\python.exe scripts/ci/run_tests.py --suite backend
.\.venv\Scripts\python.exe scripts/ci/evaluate_rag.py
```

`evaluation/measure_retrieval.py` compares retrieval with a historical Git revision using in-memory indexes, hash embeddings and a token-overlap reranker. It requires backend test dependencies and Git history; it does not call an LLM or modify persistent indexes. Its timing results are developer measurements, not production-model quality claims.

```powershell
.\.venv\Scripts\python.exe scripts/evaluation/measure_retrieval.py --baseline b257f3cdec8a3060029ea7710a9e12e896293969 --output backend/data/evaluation/generated/offline_retrieval_review.json
```

Keep generated reports in the ignored output directory. Production images include canonical Markdown documents and evaluation labels; alternate-format fixtures remain in the repository for format-parity tests.
