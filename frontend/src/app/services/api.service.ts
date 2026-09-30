import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import {
  AgentComparisonResponse,
  AgentRequest,
  AgentResponse,
  AnswerResponse,
  HealthResponse,
  IngestResponse,
  InspectResponse,
  McpLookupResponse,
} from '../models/types';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiUrl || '/api';

  health(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(`${this.baseUrl}/health`);
  }

  ask(question: string, documentType?: 'contract' | 'amendment'): Observable<AnswerResponse> {
    return this.http.post<AnswerResponse>(`${this.baseUrl}/ask`, {
      question,
      document_type: documentType,
    });
  }

  inspect(question: string, documentType?: 'contract' | 'amendment'): Observable<InspectResponse> {
    return this.http.post<InspectResponse>(`${this.baseUrl}/inspect`, {
      question,
      document_type: documentType,
    });
  }

  ingest(): Observable<IngestResponse> {
    return this.http.post<IngestResponse>(`${this.baseUrl}/ingest`, {});
  }

  runAgent(request: AgentRequest): Observable<AgentResponse | AgentComparisonResponse> {
    return this.http.post<AgentResponse | AgentComparisonResponse>(
      `${this.baseUrl}/agent`,
      request,
    );
  }

  mcpLookup(contractId: string): Observable<McpLookupResponse> {
    return this.http.post<McpLookupResponse>(`${this.baseUrl}/mcp/lookup`, {
      contract_id: contractId,
    });
  }
}
