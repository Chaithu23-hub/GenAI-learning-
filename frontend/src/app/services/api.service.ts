import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { AskResponse, Backend } from '../models/types';
import { environment } from '../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private http = inject(HttpClient);
  // Use the Angular dev-server proxy locally and the configured API URL in deployments.
  private apiUrl = environment.apiUrl || '/api';

  askQuestion(query: string, backend: Backend): Observable<AskResponse> {
    const headers = new HttpHeaders({
      'Content-Type': 'application/json',
      'X-API-Key': 'dev-key-123'
    });

    const body = {
      question: query,
      backend: backend === 'auto' ? null : backend,
    };

    return this.http.post<AskResponse>(`${this.apiUrl}/ask`, body, { headers });
  }
}
