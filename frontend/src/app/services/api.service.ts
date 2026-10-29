import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { AnswerResponse } from '../models/types';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiUrl || '/api';

  ask(question: string, documentType?: 'contract' | 'amendment'): Observable<AnswerResponse> {
    return this.http.post<AnswerResponse>(`${this.baseUrl}/ask`, {
      question,
      document_type: documentType,
    });
  }
}
