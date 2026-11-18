# Week 3–12 Tasks and Implementation

Reviewed: 18 November 2026. Selected track: **F — Legal contracts**.
**Partial** means code or reports exist, but some required measurements or demonstrations remain unverified.

| Week | Task | Implemented | Selected approach / Git branch |
| --- | --- | --- | --- |
| 3 | Build document RAG with citations and refusals. | **Core implemented:** Markdown/DOCX/text-PDF loading, section-aware chunking, embeddings, persistent search, grounded answers and unsupported-question refusals. **Remaining:** measured chunk-size comparison. | Section chunking, MiniLM, Chroma; early commits `327f4c5`, `d6c8fbc`. |
| 4 | Diagnose retrieval failures and measure one improvement. | **Implemented:** inspection endpoint, metadata filtering, dense/lexical fusion and cross-encoder reranking. **Remaining:** original controlled before/after results isolating one change. | Dense + BM25/RRF + cross-encoder; early commits and `week5`. |
| 5 | Review 20 traces and rank failure modes. | **Recorded:** 20 query/expected/actual/failure notes and five error categories used in later evaluation. **Remaining:** complete frequency × severity ranking and sampling evidence. | Manual error analysis; `week5`. |
| 6 | Build regression evals and validate the judge. | **Implemented:** 26 labelled questions, three deterministic assertions and judge infrastructure. Historical notes report **84% → 92%** agreement. **Remaining:** reproducible blind-validation evidence and current integrated agreement. | Assertions + LLM judge; `week6`, later artifacts in `week11`. |
| 7 | Compare a bounded agent with a fixed workflow. | **Implemented:** visible tool steps, fixed-workflow counterpart, definitions/version parameter and iteration/token/cost/time checks. **Remaining:** measured ten-case dependency/race evidence and saved termination log. | Custom agent versus workflow; `week7`. |
| 8 | Evaluate trajectories and defend against injection. | **Implemented:** trajectory predicates, injection detection/sanitization and defensive tests. **Remaining:** ten-case trajectory metrics, outcome–trajectory gap and measured mitigation overhead. | Trajectory checks and injection guardrails; `week8`. |
| 9 | Discover MCP tools and expose an own server. | **Implemented locally:** runtime discovery and two servers; historical artifacts record **2 → 5 tools**, annotated JSON-RPC and recoverable-error examples. **Remaining:** independent peer call and complete zero-agent-diff proof. | Stdio MCP, clause search and contract repository; `WEEK_9`. |
| 10 | Race single versus multi-agent and test worker failure. | **Implemented/recorded:** manager + two specialists, same-case race, token/cost estimates, failure retry/degradation and keep/kill verdict. **Remaining:** full handoff log. AgentCard/lifecycle research exists; live A2A is unverified. | Custom orchestrator + two workers; `week10`, `week-10-feedback-fix`. |
| 11 | Find a bad citation, add a regression, and measure cost/load. | **Implemented/recorded:** citation-consistency regression, historical RED/GREEN results, prompt-version change, canary/rollback notes and cost/load reports. **Remaining:** human drill and current Groq cost/load measurements. | Citation validation, structured tracing; `week11`. |
| 12 | Integrate RAG, agents, MCP, evals and observability. | **Implemented:** FastAPI/Angular app, Docker setup, shared contract corpus, 32-case evaluator and optional Langfuse monitoring. **Remaining:** integrated judge/trajectory/OCR measurements, complete cross-MCP trace, peer review and demo bundle. | Contract Review Assistant; `week_11_shared_corpus`, `week_12`, current `main`. |

## Additional work completed

- **Application hardening:** strengthened clause/page references, source/excerpt validation, document-version consistency and regression coverage.
- **Conversation:** added LLM-generated greetings and unsupported-question responses, with separate sampling settings and intent routing.
- **Observability and security:** added optional Langfuse tracing with content-capture controls/redaction, request IDs, reader/admin authorization and credential checks.
- **Delivery and maintenance:** improved Docker build caching, setup documentation and CI; reviewed dependency PRs, applied compatible updates and closed superseded/incompatible proposals.
- **Latest verified integration:** **660 non-slow backend tests** passed; frontend build/headless tests, clean CI security audit and RAG evaluation passed before PR **#41** was merged. These checks do not establish the missing assignment measurements above.

Historical results are not current-model benchmarks. Based on the 15 supplied briefs/task sheets, repository code and weekly Git history; no new experiments were run for this summary. See [README](../../README.md), [architecture](../../ARCHITECTURE.md) and [merged PR #41](https://github.com/Chaithu23-hub/GenAI-learning-/pull/41) for implementation and validation context.
