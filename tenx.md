# 10x Workload View

At a 10-request concurrent burst on the configured Gemini free tier, **the provider rate limit breaks first: 5/10 generation calls returned HTTP 429 against the observed 5-requests/minute/model quota**; all ten application responses were grounded because five fell back to extraction.

The burst completed in 5.552 s wall time (request latency p50 4.453 s, max 5.522 s). This is direct evidence for a 10-request burst, not a measured production baseline multiplier; today's baseline QPS was not supplied.

Paid-tier cost estimate for ten requests matching the separate live probe: `10 × $0.0024668 = $0.024668`. On the observed free tier, actual provider charge for the burst was `$0.00`; five generation requests were throttled, so the paid-tier estimate is a comparison, not the burst's bill.
