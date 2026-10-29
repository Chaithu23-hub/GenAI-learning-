import { signal, WritableSignal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { AppComponent } from './app.component';
import { HistoryItem } from './models/types';
import { QaStateService } from './services/qa-state.service';

describe('Chat workspace', () => {
  let qa: {
    history: WritableSignal<HistoryItem[]>;
    isLoading: WritableSignal<boolean>;
    hasHistory: WritableSignal<boolean>;
    ask: jasmine.Spy;
    reset: jasmine.Spy;
  };

  beforeEach(async () => {
    qa = {
      history: signal<HistoryItem[]>([]),
      isLoading: signal(false),
      hasHistory: signal(false),
      ask: jasmine.createSpy('ask'),
      reset: jasmine.createSpy('reset'),
    };
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [{ provide: QaStateService, useValue: qa }],
    }).compileComponents();
    spyOn(window, 'scrollTo');
  });

  it('submits a trimmed question and clears the composer', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.componentInstance.query = '  What is the late payment fee?  ';
    fixture.detectChanges();
    fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit'));
    expect(qa.ask).toHaveBeenCalledOnceWith('What is the late payment fee?');
    expect(fixture.componentInstance.query).toBe('');
  });

  it('disables sending while a response is pending', () => {
    qa.isLoading.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    fixture.componentInstance.query = 'Hello';
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('button[type="submit"]').disabled).toBeTrue();
  });

  it('renders formatted answers without exposing supporting metadata', () => {
    qa.history.set([{
      question: 'What is the notice period?',
      answer: 'Give **30 days** written notice.',
      reasoning: 'Internal evidence summary',
      sources: [{ document: 'contract.md', chunk_id: 'contract::001', excerpt: 'Source excerpt' }],
    }]);
    qa.hasHistory.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const content = fixture.nativeElement as HTMLElement;
    expect(content.querySelector('.answer-text strong')?.textContent).toBe('30 days');
    expect(content.textContent).not.toContain('Internal evidence summary');
    expect(content.textContent).not.toContain('contract.md');
  });

  it('clears the conversation when New chat is selected', () => {
    qa.hasHistory.set(true);
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('button[title="Clear the current conversation"]') as HTMLButtonElement).click();
    expect(qa.reset).toHaveBeenCalledOnceWith();
  });
});
