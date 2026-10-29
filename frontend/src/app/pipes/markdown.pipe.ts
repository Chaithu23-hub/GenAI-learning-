import { Pipe, PipeTransform } from '@angular/core';
import { marked } from 'marked';

@Pipe({ name: 'markdown', standalone: true })
export class MarkdownPipe implements PipeTransform {
  transform(value: string): string {
    // Angular sanitizes this string when it is bound to innerHTML.
    return marked.parse(value, { async: false, breaks: true });
  }
}
