import { Component, Input, ElementRef, ViewChild, AfterViewChecked } from '@angular/core';
import { HistoryItem } from '../../models/types';
import { BadgeComponent } from '../badge/badge.component';
import { SourceCardComponent } from '../source-card/source-card.component';

@Component({
  selector: 'app-chat-panel',
  standalone: true,
  imports: [BadgeComponent, SourceCardComponent],
  templateUrl: './chat-panel.component.html',
  styles: ``
})
export class ChatPanelComponent implements AfterViewChecked {
  @Input({ required: true }) history: HistoryItem[] = [];
  
  @ViewChild('scrollBottom') private scrollBottom!: ElementRef;

  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  private scrollToBottom(): void {
    try {
      window.scrollTo(0, document.body.scrollHeight);
    } catch(err) { }
  }
}
