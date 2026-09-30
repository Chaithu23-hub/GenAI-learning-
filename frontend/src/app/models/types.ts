// Response contract mirrored from backend/legal_rag/domain/response_schema.py

export type Confidence = 'high' | 'medium' | 'low';

export interface SourceCitation {
  document: string;
  chunk_id: string;
  excerpt: string;
}

export interface AnswerResponse {
  answer: string;
  reasoning: string;
  sources: SourceCitation[];
  confidence: Confidence;
  out_of_scope: boolean;
}

export interface RetrievedChunk {
  chunk_id: string;
  document: string;
  document_type: 'contract' | 'amendment' | string;
  heading: string;
  text: string;
  distance: number;
  score: number;
}

export interface InspectResponse {
  question: string;
  retrieved: RetrievedChunk[];
  answer: AnswerResponse;
}

export interface IngestResponse {
  chunks_ingested: number;
  message: string;
}

export interface HealthResponse {
  status: string;
  embedding_model: string;
  rerank_model: string;
  llm_provider: string;
  llm_model: string;
  vector_store_path: string;
  api_key_configured: boolean;
}

export type AgentStrategy = 'agent' | 'fixed' | 'compare';

export interface AgentRequest {
  question: string;
  strategy?: AgentStrategy;
  runs?: number;
}

export interface AgentResponse {
  strategy: string;
  result: AnswerResponse;
  steps: Array<Record<string, unknown>>;
  tool_calls: number;
  elapsed_seconds: number;
  completed: boolean;
  stop_reason: string;
  estimated_cost_usd: number;
  token_count: number;
  budget_log: string[];
}

export interface AgentComparisonResponse {
  query: string;
  agent: Record<string, unknown>;
  fixed_workflow: Record<string, unknown>;
  ship_recommendation: string;
  recommendation_reason: string;
}

export interface McpLookupResponse {
  discovered: Record<string, string[]>;
  trace: {
    server: string;
    tool: string;
    content: Array<{ type?: string; text?: string; [k: string]: unknown }>;
  };
}

// RFC 7807 problem+json shape produced by the backend error handlers.
export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail: string;
  request_id?: string;
}

// Local UI-side history entry. `pendingId` is a stable id for in-flight items
// so the state service can update them even if the list mutates.
export interface HistoryItem {
  question: string;
  answer?: string;
  reasoning?: string;
  sources?: SourceCitation[];
  confidence?: Confidence;
  out_of_scope?: boolean;
  isLoading?: boolean;
  error?: string;
  pendingId?: number;
}
