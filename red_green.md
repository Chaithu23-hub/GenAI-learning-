# RED / GREEN Evidence

## RED

The citation guard was temporarily disabled to prove the Week 6 case fails:

```text
python -m pytest tests -q
1 failed, 200 passed in 42.59s
```

The failing test returned “Section 3 permits…” while the only citation was the Section 5 termination chunk.

## GREEN

After restoring the section-reference guard:

```text
python -m pytest backend/tests/integration/test_termination_citation_eval.py -q
1 passed in 0.04s

python -m pytest tests -q
201 passed in 41.04s
```

The final suite includes the Week 6 ID 26 citation regression and real Chroma/SentenceTransformer retrieval evaluation.

## Final verification after model fallback fix

The live API check exposed and fixed a separate fallback-selection defect. Final verification:

```text
python -m pytest tests -q
204 passed in 42.57s

python -m ruff check backend
All checks passed!
```

After adding trace coverage for provider 429 fallback, the final suite passed `205 passed in 41.94s`; the backend-wide Ruff check again reported `All checks passed!`.
