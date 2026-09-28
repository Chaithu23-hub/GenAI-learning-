# Worker failure case

Case: Week 6 id 10: "What does incorporation mean?" (human label: False)
Injected: `defined_terms_worker` raises HTTP 500 on every call for this case (`run_orchestrator(..., fail_worker="defined_terms")`). Terms requested: ['incorporation'].
Retry policy under test: `config.ORCHESTRATOR_WORKER_RETRIES = 1`.

**What the orchestrator actually did: retried 1x, then degraded to a partial answer and stated no meaning for the unverified term.**

- defined-terms attempts: 2 (statuses [500, 500]); retried=True, degraded=True, lied=False
- judge on the faulted run: fail (checks {'clause_references_exist': True, 'effective_dates_parseable': True, 'notice_periods_numeric': True, 'answered': False, 'sources_verified': False, 'on_topic': False})
- tokens: faulted run 2,303 vs clean run 2,115; latency 0.623s vs 0.660s

## Final answer returned (faulted run)

```json
{
  "answer": "I don't know — this information is not in the provided documents.",
  "reasoning": "No retrieved chunk scored above the relevance threshold, so the knowledge base contains no grounded answer for this question. [Partial answer] The meaning of \"incorporation\" could not be verified: the defined-terms worker returned HTTP 500, so no definition is given.",
  "sources": [],
  "confidence": "low",
  "out_of_scope": true
}
```

## Hand-offs (faulted run)

| hop | tokens | status | attempt |
|---|---:|---:|---:|
| user -> orchestrator (plan) | 140 | 200 | 1 |
| orchestrator -> clause_worker (brief + retrieved chunks) | 1540 | 200 | 1 |
| orchestrator -> defined_terms_worker | 174 | 500 | 1 |
| orchestrator -> defined_terms_worker | 174 | 500 | 2 |
| workers -> synthesizer (clause answer + definitions) | 275 | 200 | 1 |
