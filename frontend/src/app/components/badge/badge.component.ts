import { Component, Input } from '@angular/core';
import { TitleCasePipe } from '@angular/common';

@Component({
  selector: 'app-badge',
  standalone: true,
  imports: [TitleCasePipe],
  template: `
    <span class="badge" [class]="'badge-' + confidence">
      {{ confidence | titlecase }} Confidence
    </span>
  `,
  styles: []
})
export class BadgeComponent {
  @Input() confidence: 'high' | 'medium' | 'low' = 'medium';
}
