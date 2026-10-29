import { Component, Input, AfterViewChecked } from '@angular/core';
import { HistoryItem } from '../../models/types';
import { MarkdownPipe } from '../../pipes/markdown.pipe';

@Component({
  selector: 'app-chat-panel',
  standalone: true,
  imports: [MarkdownPipe],
  templateUrl: './chat-panel.component.html',
  styles: ``
})
export class ChatPanelComponent implements AfterViewChecked {
  @Input({ required: true }) history: HistoryItem[] = [];
  
  private lastHistory: HistoryItem[] | null = null;

  ngAfterViewChecked() {
    if (this.lastHistory === this.history) return;
    this.lastHistory = this.history;
    window.scrollTo(0, document.body.scrollHeight);
  }
}
