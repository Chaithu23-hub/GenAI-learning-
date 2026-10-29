// Response contract mirrored from backend/legal_rag/domain/response_schema.py.
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

// RFC 7807 problem+json returned by the backend error handlers.
export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail: string;
  request_id?: string;
}

// Local history retains a stable ID while a request is in flight.
export interface HistoryItem extends Partial<AnswerResponse> {
  question: string;
  isLoading?: boolean;
  error?: string;
  pendingId?: number;
}
