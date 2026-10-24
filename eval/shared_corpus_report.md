# Shared Corpus Golden Evaluation

Format: `md`; provider: `google`; documents: 6; chunks: 170.
Overall pass rate: **28/32**

## By class

| Class | Passed | Total |
|---|---:|---:|
| direct_lookup | 7 | 8 |
| amendment_supersession | 7 | 7 |
| counterparty_disambiguation | 4 | 4 |
| out_of_scope | 2 | 4 |
| defined_term_chase | 3 | 3 |
| multi_hop_dependent | 2 | 2 |
| computation | 1 | 2 |
| version_comparison | 1 | 1 |
| cross_document | 1 | 1 |

## Failure breakdown

| Failure | Count |
|---|---:|
| fail_wrong_version | 0 |
| fail_wrong_counterparty | 0 |
| fail_hallucination | 4 |
| fail_false_refusal | 0 |

## Cases

| Case | Class | Result | Reason |
|---|---|---|---|
| GS-001 | direct_lookup | PASS | Late payment interest stays at 1.5% per month; amendment confirms it is unchanged. |
| GS-002 | direct_lookup | PASS | Governing law is Indian law; Chennai is the registered office and dispute venue in the agreement. |
| GS-003 | direct_lookup | PASS | Payment due date is 30 days after invoice under the agreement as amended. |
| GS-004 | direct_lookup | PASS | The cure period is 45 days under the Northwind agreement as amended. |
| GS-005 | amendment_supersession | PASS | Termination notice is 15 Business Days under the latest amendment. |
| GS-006 | counterparty_disambiguation | PASS | Northwind Section 8.3 cap is USD 5,000,000 or 12-month fees; Vertex differs. |
| GS-007 | amendment_supersession | PASS | Confidentiality survival is 7 years under the amended Northwind agreement. |
| GS-008 | amendment_supersession | PASS | Liability cap is amended to the greater of USD 5m or 12 months of fees. |
| GS-009 | amendment_supersession | PASS | The liability cap and confidentiality survival are taken from the controlling amendment. |
| GS-010 | defined_term_chase | PASS | Business Day uses the holiday schedule in Schedule C. |
| GS-011 | defined_term_chase | PASS | Schedule C defines the holiday calendar that applies to Business Day. |
| GS-012 | amendment_supersession | PASS | The current version controls; earlier 60-day and 2m numbers are superseded. |
| GS-013 | multi_hop_dependent | PASS | Breach notice deadlines flow through Schedule B-2 and the cure period clause. |
| GS-014 | multi_hop_dependent | PASS | Service Failure and Qualifying Event are chained through service levels and schedules. |
| GS-015 | direct_lookup | PASS | Schedule B tables specify fees and service levels; the relevant values are in the schedule. |
| GS-016 | direct_lookup | PASS | The default fee schedule/ service performance terms were retrieved from the correct schedule. |
| GS-017 | direct_lookup | PASS | The clause references a specific schedule and its defined table values. |
| GS-018 | computation | PASS | The calculation is based on the schedule table and service thresholds. |
| GS-019 | computation | FAIL | Missed the exact threshold or calculation output in the table-driven service level case. |
| GS-020 | version_comparison | PASS | The controlling amendment version is the latest under the amendment chain. |
| GS-021 | cross_document | PASS | The answer requires combining the agreement and the relevant schedule or amendment. |
| GS-022 | direct_lookup | PASS | The dispute clause is correctly identified from the agreement text. |
| GS-023 | direct_lookup | PASS | The correct clause value is taken from the applicable agreement text. |
| GS-024 | counterparty_disambiguation | PASS | The Vertex agreement sets the cap at USD 500,000, not the Northwind value. |
| GS-025 | counterparty_disambiguation | PASS | Dispute resolution under Vertex is SIAC arbitration seated in Singapore. |
| GS-026 | counterparty_disambiguation | PASS | Vertex cure period is 20 days, distinct from the Northwind amendment values. |
| GS-027 | direct_lookup | PASS | Confidentiality survives for 3 years, and trade secrets survive indefinitely while secret. |
| GS-028 | direct_lookup | PASS | Liability cap is EUR 50,000, with a carve-out for breach of Section 3. |
| GS-029 | out_of_scope | FAIL | No Apex Industries agreement exists in the corpus; model should refuse. |
| GS-030 | out_of_scope | PASS | No separate holiday calendar exists for Vertex; it uses Singapore public holidays. |
| GS-031 | out_of_scope | PASS | Service SVC-05 is not in the corpus, so the answer should be a refusal. |
| GS-032 | out_of_scope | PASS | No amendments exist for the Vertex agreement; the system should not import Northwind values. |

