---
name: model-routing
description: Choose among available AI models by task requirements, demonstrated strengths, cost, and latency. Use when the user requests model selection, model routing, or assigning different models to different kinds of work.
---

# Model routing

Match the task to an available model's verified capabilities. Treat expertise as evidence from relevant evaluations and observed results, rather than a permanent ranking by provider or model name.

## Establish the selection boundary

Distinguish between choosing a model for the coding assistant and choosing an LLM inside the user's application. Changing an application provider does not change the assistant's model, and writing this skill does not install an automatic runtime router.

Discover available model identifiers and controls from the current environment or the application's settings and adapters. Preserve an explicit user choice. If switching is unavailable, explain the recommended selection without claiming it has been applied. Delegation and model overrides remain subject to the session's instructions; this skill does not authorize spawning agents.

## Match capabilities to the work

Use this table to identify the required capability, then select a supported model with evidence that it meets it. A single model may cover several rows.

| Work | Capability to prioritize | Evidence to check |
| --- | --- | --- |
| Small edits, formatting, routine summaries, greetings | Low latency and low cost with adequate instruction following | Correct output on a representative example |
| Implementing features, refactoring, debugging | Code understanding, repository navigation, reliable tool use | Relevant tests, lint, and observed patch quality |
| Architecture, difficult bugs, complex tradeoffs | Strong reasoning and sustained consistency | Explicit assumptions, competing explanations, and verification |
| Contract questions and document extraction | Grounded answers, exact extraction, structured output | Current clauses, amendment precedence, missing-information behavior, and schema validity |
| Large document sets | Sufficient context capacity and retrieval quality | Relevant evidence retained across the input; do not equate context size with accuracy |
| Screenshots, diagrams, scanned pages | Native image input or an appropriate OCR pipeline | Actual visual details read correctly; text-only models cannot directly inspect images |
| External tools and agent workflows | Supported tool calling and dependable argument generation | Valid calls, correct tool-result handling, and bounded execution |
| Review of consequential changes | Careful reasoning and relevant review performance | Findings supported by code or tests; another model's agreement alone is not proof |

Do not hardcode claims such as one provider always being best at coding or another always being best at legal analysis. For a named model recommendation, verify current official documentation for availability, modalities, context limits, tool support, and pricing. Use task-specific evaluations to judge quality; label an untested selection as provisional.

## Select economically and escalate deliberately

Start with the least expensive available model that meets the task's quality and feature requirements. Spend more reasoning effort on ambiguity, interacting constraints, and failures that require diagnosis. Keep straightforward tasks on a fast option when its outputs are adequate.

Respect the user's budget. For this user's LegalRAG application, prefer free API tiers unless they authorize spending. Verify quota and model eligibility before calling a tier free. Do not infer API credit from a consumer chat subscription or silently fall back to a paid provider.

Escalate after a concrete quality failure, such as invalid structured output, failed tests, an unresolved reasoning error, or omission of a controlling amendment. First check whether the problem is retrieval, configuration, or missing context; a stronger generator cannot recover evidence it never received. Use a bounded retry or a clearly justified next model rather than cycling through providers.

For rate limits and outages, use the configured retry and fallback policy. Do not repeatedly retry exhausted credits or invent a replacement model identifier. Explain when a fallback changes available features or answer quality. Preserve privacy constraints when considering another provider.

## Apply and verify within scope

When asked only for a recommendation, give the selected model or capability profile and one concrete reason. When a supported switch is requested, apply it through the existing configuration or model-selection control and verify the effective selection. Never print API keys.

For LegalRAG implementation work, follow the repository's current AGENTS.md: keep model configuration in Settings, external calls behind ports and adapters, and composition in the container. A model-selection request does not by itself require adding an automatic router or changing the response contract.

Validate application model changes with representative questions covering a normal contract clause, an overriding amendment, unavailable information, and general conversation where supported. Check grounding and qualifications as well as response style. Report what was actually tested and any remaining uncertainty.

Useful invocations:

- "Use $model-routing to choose a free model for contract Q&A with structured output."
- "Use $model-routing to select an available coding model for this difficult backend bug."
- "Use $model-routing to compare a fast model and a reasoning model on our evaluation cases."
