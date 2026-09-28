# Verdict: kill the orchestrator (fold its two cheap ideas into the single agent)

Sunk-cost bias, named out loud: we built this orchestrator last week, and that effort is a reason we *want* to keep it. It is not evidence, so it gets no weight here.
Pass rate: 20% (2/10) single vs 20% (2/10) orchestrator. Both arms pass the same two cases (2, 3) and fail the other 8 for the same reason: retrieval refuses them before either architecture gets involved.
Tokens: 16,055 orchestrator vs 34,280 single (0.5x multiplier). Cost per question: $0.001605 vs $0.003428. p99 latency: 0.660 s vs 1.296 s.
The orchestrator is cheaper and faster, but that is our context strategy, not the pattern: it trims chunks to 600 chars and retrieves once. Given the same untrimmed chunks, the multiplier rises to 0.7x.
The rest of the gap exists because the single agent re-sends its ~1,060-token prompt plus 4 tool schemas every turn and retrieves twice. Both are fixable in the single agent in a few lines.
The orchestrator also adds failure surface. It over-delegates (case 4's "What is the difference…" is sent to the defined-terms worker for nothing), and the injected 500 cost 2 extra hops plus a synthesis hop, only to return the same refusal.
Decision: kill it. Port chunk trimming and single retrieval into the single agent, and spend the effort on the retrieval bug. Filtering "amendment" questions to `document_type=amendment` is why 8/10 fail.
What would flip this: an orchestrator pass rate above the single agent's on these same 10 cases, once both use the same context strategy.
