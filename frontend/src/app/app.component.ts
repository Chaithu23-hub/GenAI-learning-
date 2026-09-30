import { Component, inject, signal } from '@angular/core';
import { KeyValuePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';

import { ChatPanelComponent } from './components/chat-panel/chat-panel.component';
import { ApiService } from './services/api.service';
import { QaStateService } from './services/qa-state.service';
import { McpLookupResponse } from './models/types';
import { ApiError } from './core/error.interceptor';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [FormsModule, KeyValuePipe, ChatPanelComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css',
})
export class AppComponent {
  readonly suggestions = [
    'What is the late payment fee?',
    'When does the agreement expire?',
    'What does the amendment change?',
  ];

  query = '';
  readonly qa = inject(QaStateService);
  private readonly api = inject(ApiService);

  // Keep template access simple.
  get history() { return this.qa.history(); }
  get isLoading() { return this.qa.isLoading(); }

  readonly mcpLoading = signal(false);
  readonly mcpResult = signal<McpLookupResponse | null>(null);
  readonly mcpError = signal('');

  useSuggestion(question: string) {
    this.query = question;
    document.getElementById('question-input')?.focus();
  }

  handleSubmit(event: Event) {
    event.preventDefault();
    const q = this.query.trim();
    if (!q) return;
    this.query = '';
    this.qa.ask(q);
  }

  newChat() {
    this.qa.reset();
    this.query = '';
  }

  runMcpLookup() {
    this.mcpLoading.set(true);
    this.mcpError.set('');
    this.mcpResult.set(null);
    this.api
      .mcpLookup('MSA-2021-0142')
      .pipe(finalize(() => this.mcpLoading.set(false)))
      .subscribe({
        next: (response) => this.mcpResult.set(response),
        error: (err: ApiError | Error) => {
          const message =
            err instanceof ApiError
              ? `${err.message}${err.requestId ? ` (request ${err.requestId})` : ''}`
              : 'MCP lookup failed. Check that the API and configured servers are running.';
          this.mcpError.set(message);
        },
      });
  }
}
