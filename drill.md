# Week 11 Production Drill

## Find result

- Time-to-find: **00:00** (0.003 seconds measured) for the controlled RED log, searched by GitHub Copilot's automated `answer_clause_refs` output slice. No human squadmate performed the timed search, and no historical planted request was available.
- Planning estimate for a human using the indexed output field: **00:30**; this is an estimate only and must not be substituted for the squadmate's timed result. **I have not verified this estimate with a squadmate.**
- Slice: **answer/output**. The complaint identifies the cited termination section, so indexing only query input would miss the signal.
- Exact missing field: **`answer_clause_refs`**. The previous QA log did not index clause references from generated answers. The v2 trace now records the output references and candidate references from every generation span.
- The Week 11 case is reproduced as a controlled regression, not presented as the lawyer's historical request.
- One live cost probe confirmed the configured model was retired; runtime selection now switches to the API-listed `models/gemini-2.5-flash` and the request succeeds.

## Failure and fix

The controlled RED run returned a Section 3 termination claim while citing the retrieved Section 5 termination chunk. The source check verified the chunk and excerpt but did not verify that the answer's section number appeared in that cited source.

The v2 prompt requires section-number consistency, and the generator now validates answer references against the retrieved cited source. Invalid output is retried once, then falls back to extractive evidence. Week 6 label ID 26 records the new negative case; IDs 1–25 are unchanged.

## Prompt rollout

Canary: Route 5% of legal QA traffic to `qa.system@v2` for one hour; promote only with zero observed section/source mismatches and no more than 10% latency regression.
Rollback: Repin `qa.system` to retained `v1`, redeploy, and verify the health prompt snapshot reports `v1`.

## Evidence

- RED: `1 failed, 200 passed`; the failure was the new unsupported-section regression.
- GREEN: `201 passed`; the full backend suite passed with the citation guard restored.
- Final after model-fallback and 429 trace corrections: `205 passed`; Ruff passed.
- 10x free-tier burst: 10 concurrent QA requests completed in 5.552 s; five Gemini calls succeeded, five were HTTP 429 at the observed 5 RPM/model limit, and all ten returned grounded answers via five extractive fallbacks.
- Cost: free-tier provider charge was `$0.00`; the five successful calls used 3,770 input and 1,436 output tokens, equivalent to `$0.004721` at paid list prices.
- Real legal-corpus retrieval: 7/10 hit-rate@3 dense and 7/10 hybrid; 58 chunks from five documents.
- Cost for the historical complaint is unavailable. Controlled fake-client token and latency measurements are in `trace.json`; they are not billable production usage.
- Separate live probe: 1,006 input tokens, 866 output tokens; estimated `$0.002467` at published paid-tier pricing. This is not the missing historical complaint trace.
- Proxy estimate for the missing request: `$0.002467/query` if it had the same token usage, model, and paid-tier rates as the separate live probe; actual historical cost remains unknown.
- The automated search took `00:00.003`; no named human squadmate timed it. No historical planted complaint trace was found.
