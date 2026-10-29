import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ChatPanelComponent } from './components/chat-panel/chat-panel.component';
import { QaStateService } from './services/qa-state.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [FormsModule, ChatPanelComponent],
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

  // Keep template access simple.
  get history() { return this.qa.history(); }
  get isLoading() { return this.qa.isLoading(); }

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

}
