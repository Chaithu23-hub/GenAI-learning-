import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ChatPanelComponent } from './components/chat-panel/chat-panel.component';
import { ApiService } from './services/api.service';
import { HistoryItem } from './models/types';
import { finalize } from 'rxjs';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [FormsModule, ChatPanelComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent {
  suggestions = [
    'What is the late payment fee?',
    'When does the agreement expire?',
    'What does the amendment change?'
  ];

  query: string = '';
  isLoading: boolean = false;
  history: HistoryItem[] = [];

  private apiService = inject(ApiService);

  useSuggestion(question: string) {
    this.query = question;
    document.getElementById('question-input')?.focus();
  }

  handleSubmit(event: Event) {
    event.preventDefault();
    if (!this.query.trim()) return;

    const currentQuery = this.query;
    this.query = '';
    this.isLoading = true;

    // Add user question to history
    this.history.push({
      question: currentQuery,
      isLoading: true
    });

    const index = this.history.length - 1;

    this.apiService.askQuestion(currentQuery)
      .pipe(
        finalize(() => {
          this.isLoading = false;
        })
      )
      .subscribe({
        next: (response) => {
          this.history[index] = {
            ...this.history[index],
            ...response,
            isLoading: false
          };
        },
        error: (err) => {
          this.history[index] = {
            ...this.history[index],
            isLoading: false,
            error: 'Failed to connect to the legal assistant backend.'
          };
          console.error(err);
        }
      });
  }
}
