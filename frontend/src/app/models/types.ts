export type Backend = 'auto' | 'llm' | 'extractive';

export interface SourceCitation {
  document: string;
  chunk_id: string;
  excerpt: string;
}

export interface AskResponse {
  answer: string;
  reasoning: string;
  sources: SourceCitation[];
  confidence: 'high' | 'medium' | 'low';
  out_of_scope: boolean;
}

export interface HistoryItem {
  question: string;
  answer?: string;
  reasoning?: string;
  sources?: SourceCitation[];
  confidence?: 'high' | 'medium' | 'low';
  out_of_scope?: boolean;
  isLoading?: boolean;
  error?: string;
}
