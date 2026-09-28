# Bonus: the failed case on the A2A task lifecycle

AgentCard: [agent_card.json](agent_card.json). It advertises 2 skills, text in and JSON out, and `X-API-Key` header auth, which is the same header `app/dependencies.py` enforces.

## Case 10 ("What does incorporation mean?") with the defined-terms worker returning 500

| A2A state | What happened |
|---|---|
| `submitted` → `working` | Orchestrator planned `clause` + `defined_terms(["incorporation"], version="amended")` |
| clause subtask `completed` | Clause worker retrieved chunks; none cleared the relevance threshold, so it returned out-of-scope |
| defined-terms subtask `failed` | Two attempts, both HTTP 500 |
| parent task: **`completed`** (actual) | Synthesiser returned "I don't know — this information is not in the provided documents." and noted the 500 only in `reasoning` |

**It should have ended `failed`, not `input-required`.** `input-required` means the user can supply the missing fact, and no user can fix a worker's 500. Returning `completed` with "not in the documents" also blames the corpus for what was a server fault, so the parent should surface the worker failure as `failed`.

**Where `input-required` *is* right:** asking the late-payment question against this corpus. `amendment_01_payment_terms.md` carries no effective date, so it is unclear whether 1.0% (MSA, effective 2021-01-14) or 1.5% (Amendment No. 1) governs on a given invoice date. Today the orchestrator silently assumes `governing_version="amended"`. It should pause at `input-required` and ask which amendment date governs.

## What A2A buys over a plain REST call to the worker

A REST 500 carries only "it broke". An A2A task has an id and typed states (`working`, `input-required`, `failed`, `completed`), so the orchestrator can pause, ask the user, and resume the same task instead of guessing.
The AgentCard also makes the worker's skills, I/O modes and auth discoverable as a contract, so the orchestrator is not hard-coding an endpoint and a payload shape.
