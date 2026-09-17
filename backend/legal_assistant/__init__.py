# legal_assistant — top-level package
# Sub-packages group modules by responsibility:
#   ingestion/   — chunking, embeddings, vector store
#   retrieval/   — hybrid search + cross-encoder re-rank
#   generation/  — extractive & LLM generators, schema, pipeline
#   safety/      — input guardrails, injection detection
#   agent/       — agentic loop, MCP host, race evaluation
#   evaluation/  — offline metrics, LLM-as-judge
