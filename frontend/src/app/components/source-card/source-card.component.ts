import { Component, Input } from '@angular/core';
import { SourceCitation } from '../../models/types';

@Component({
  selector: 'app-source-card',
  standalone: true,
  templateUrl: './source-card.component.html',
  styles: ``
})
export class SourceCardComponent {
  @Input({ required: true }) source!: SourceCitation;
}
