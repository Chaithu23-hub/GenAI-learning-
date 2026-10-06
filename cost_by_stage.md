# Cost by Stage

## Controlled Citation Request

This is the instrumented fake-client RED run for Week 6 case 26, not a historical customer request. The fake client has no provider bill; local retrieval cost was not priced.

| Stage | Latency | Tokens | Controlled provider cost |
|---|---:|---:|---:|
| Retrieval | 0.262 ms | Not token-metered | $0.00 (local; compute cost not priced) |
| Generation | 0.002 ms | 10 prompt + 5 completion | $0.00 (fake client; not billable) |
| Tools | 0 calls | 0 | $0.00 |
| Total | 3.779 ms end-to-end test | 15 fake-client tokens | $0.00 provider charges |

Generation retry in the GREEN run: 0.003 ms, 0 prompt + 0 completion tokens from the empty fake response. The per-span trace is in `trace.json`.

## Historical Request

Historical per-query cost is unavailable because the squadmate-planted production trace and provider price schedule were not provided. Do not present controlled fake-client values as production usage.

**Proxy estimate only:** using the separate live probe's 1,006 input and 866 output tokens with Gemini 2.5 Flash published paid-tier pricing gives `$0.0024668/query` (about `$0.002467`). If the missing complaint had the same stage mix, retrieval-provider cost would be `$0.00` with local retrieval (local compute excluded), generation would be `$0.0024668`, and tools `$0.00`. This is not the historical request's measured cost.

## Separate Live Cost Probe

One real request to the available `models/gemini-2.5-flash` model completed after the retired configured model was detected and replaced. This is a controlled probe, not the historical bad-citation request.

| Stage | Latency | Tokens | List-price estimate |
|---|---:|---:|---:|
| Retrieval | 4,666.064 ms | Local tokens not metered | Local compute not priced |
| Generation | 6,093.633 ms | 1,006 input + 866 output | $0.0024668 |
| Tools | 0 calls | 0 | $0.00 |
| Total | 10,765.674 ms | 1,872 provider tokens | $0.0024668 |

Estimate uses published Gemini 2.5 Flash paid-tier rates of $0.30/M input and $2.50/M output tokens. Actual account billing tier was not observable; see the [official pricing page](https://ai.google.dev/gemini-api/docs/pricing).

## Free-Tier 10-Request Burst

Ten concurrent QA requests completed in 5,551.849 ms. The Gemini free-tier API quota reported a limit of 5 generation requests per minute for this model: five calls returned HTTP 200 and five returned HTTP 429. The app still returned grounded answers for all ten by using extractive fallback on the five rate-limited calls.

| Stage | Calls/outcome | Latency | Tokens | Cost |
|---|---:|---:|---:|---:|
| Retrieval + reranking | 10 initial requests; fallback added retrieval for 5 | Successful-call span p50 867.756 ms, max 975.940 ms | Local tokens not metered | Local compute not priced |
| Gemini generation | 10 attempted; 5 accepted, 5 HTTP 429 | Successful-call span p50 3,068.874 ms, max 3,285.192 ms; 429 spans not captured in this run | 3,770 input + 1,436 output = 5,206 | $0.00 free-tier charge; $0.004721 paid-list equivalent |
| Tools | 0 | 0 | 0 | $0.00 |
| Total | 10 grounded responses; 5 used fallback | Request p50 4,453.237 ms, max 5,522.265 ms; batch wall 5,551.849 ms | 5,206 provider tokens accepted | $0.00 free-tier charge |

The five 429 requests were rejected before generation and did not produce billable output tokens. The paid-list equivalent uses $0.30/M input and $2.50/M output for the five successful calls; it is a comparison value, not the free-tier bill.
