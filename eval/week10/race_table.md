# Week 10 race — single agent vs orchestrator

Cases: Week 6 `eval/labels_25.json` ids 1–10 (pre-extension sha256 `7c77f9facd56`). Week 11 later appended ID 26; IDs 1–10 and their labels remain unchanged. Current labels file sha256: `7d373d6d7432c498f777bbc4e4a4a0c272a7014ddc9ee342f83ad1d67b34ae01`.
Judge: `legal_assistant/evaluation/race_judge.py`, the same function for both arms.
Tokens: serialised payload per model call / 4 chars, same estimator both arms. Cost: tokens x $0.000001 (`config.AGENT_COST_PER_TOKEN_USD`).
Latency: warm models, arms interleaved per case, CPU. p99 is nearest-rank over 10 runs, so it is the slowest case.

| metric | single_agent | orchestrator |
|---|---:|---:|
| pass rate | 20% (2/10) | 20% (2/10) |
| p50 latency (s) | 0.090 | 0.080 |
| p99 latency (s) | 1.296 | 0.660 |
| total tokens | 34,280 | 16,055 |
| cost per question (USD) | 0.003428 | 0.001605 |

**Context re-send multiplier: 0.5x** (16,055 / 34,280). Largest share: `orchestrator -> clause_worker (brief + retrieved chunks)`, 83% of all orchestrator tokens.

## Orchestrator tokens by hand-off

| hand-off | tokens | share |
|---|---:|---:|
| orchestrator -> clause_worker (brief + retrieved chunks) | 13,298 | 82.8% |
| user -> orchestrator (plan) | 1,399 | 8.7% |
| workers -> synthesizer (clause answer + definitions) | 801 | 5.0% |
| orchestrator -> defined_terms_worker | 557 | 3.5% |

## Single-agent tokens by turn

| turn | tokens | share |
|---|---:|---:|
| single_agent turn -> answer (transcript re-read) | 23,524 | 68.6% |
| single_agent turn -> retrieve (transcript re-read) | 10,756 | 31.4% |

## Per case

| id | question | human | single pass | orch pass | single tok | orch tok | single s | orch s | orch subtasks |
|---:|---|:-:|:-:|:-:|---:|---:|---:|---:|---|
| 1 | What does the First Amendment protect? | T | fail | fail | 2,367 | 1,263 | 0.088 | 0.047 | clause_worker |
| 2 | Can the government take my property? | F | PASS | PASS | 5,129 | 1,921 | 1.055 | 0.503 | clause_worker |
| 3 | Is there a right to privacy in the Constitution? | T | PASS | PASS | 5,135 | 1,927 | 0.872 | 0.414 | clause_worker |
| 4 | What is the difference between First and Fourth Amendments? | F | fail | fail | 2,377 | 1,766 | 0.073 | 0.048 | clause_worker+defined_terms_worker+synthesizer |
| 5 | Can I be tried twice for the same crime? | T | fail | fail | 4,847 | 1,678 | 0.985 | 0.478 | clause_worker |
| 6 | What rights does the Sixth Amendment grant criminal defendants? | T | fail | fail | 2,380 | 1,275 | 0.081 | 0.038 | clause_worker |
| 7 | What is sovereign immunity under the amendments? | T | fail | fail | 2,373 | 1,724 | 0.090 | 0.106 | clause_worker+defined_terms_worker+synthesizer |
| 8 | What does the 12th Amendment change about presidential elections? | T | fail | fail | 2,381 | 1,277 | 0.090 | 0.055 | clause_worker |
| 9 | Why did the founders create the Second Amendment? | T | fail | fail | 2,388 | 1,109 | 0.042 | 0.004 | clause_worker |
| 10 | What does incorporation mean? | F | fail | fail | 4,903 | 2,115 | 1.296 | 0.660 | clause_worker+defined_terms_worker+synthesizer |

Judge vs Week 6 human label agreement: single 3/10, orchestrator 3/10.
