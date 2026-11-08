import { TestBed } from '@angular/core/testing';
import { ApiService } from './api.service';
import { QaStateService } from './qa-state.service';

describe('QaStateService persisted history', () => {
  const storageKey = 'legal_rag.chat_history.v1';
  const apiStub = { ask: jasmine.createSpy('ask') };

  beforeEach(() => {
    localStorage.removeItem(storageKey);
    TestBed.configureTestingModule({ providers: [
      QaStateService,
      { provide: ApiService, useValue: apiStub },
    ] });
  });

  afterEach(() => {
    TestBed.resetTestingModule();
    localStorage.removeItem(storageKey);
    apiStub.ask.calls.reset();
  });

  it('drops entries whose persisted answer and optional fields have invalid types', () => {
    localStorage.setItem(storageKey, JSON.stringify([
      { question: 'Valid question', answer: 'Valid answer', reasoning: 'Reason', sources: [] },
      { question: 'Invalid answer', answer: { unsafe: true } },
      { question: 'Invalid error', error: 42 },
      { question: 42, answer: 'Missing string question' },
    ]));

    const service = TestBed.inject(QaStateService);

    expect(service.history()).toEqual([
      jasmine.objectContaining({ question: 'Valid question', answer: 'Valid answer', isLoading: false }),
    ]);
  });

  it('loads at most the newest 100 valid entries', () => {
    localStorage.setItem(storageKey, JSON.stringify(
      Array.from({ length: 125 }, (_, index) => ({ question: `Question ${index}`, answer: `Answer ${index}` })),
    ));

    const service = TestBed.inject(QaStateService);

    expect(service.history()).toHaveSize(100);
    expect(service.history()[0].question).toBe('Question 25');
    expect(service.history()[99].question).toBe('Question 124');
  });

  it('persists only displayed conversation text and strips legacy hidden fields', () => {
    localStorage.setItem(storageKey, JSON.stringify([{
      question: 'Old question', answer: 'Old answer', reasoning: 'Old internal summary',
      sources: [{ document: 'private.md', chunk_id: 'private::001', excerpt: 'Legacy confidential excerpt' }],
    }]));
    const service = TestBed.inject(QaStateService);
    expect(service.history()[0]).not.toEqual(jasmine.objectContaining({ reasoning: jasmine.anything() }));
    expect(service.history()[0].sources).toBeUndefined();
    service.history.set([{
      question: 'What is the notice period?',
      answer: '30 days',
      error: 'A displayable error',
      reasoning: 'Internal evidence summary',
      sources: [{ document: 'private.md', chunk_id: 'private::001', excerpt: 'Confidential excerpt' }],
      confidence: 'high',
      out_of_scope: false,
    }]);
    TestBed.flushEffects();

    const saved = JSON.parse(localStorage.getItem(storageKey) ?? '[]') as Record<string, unknown>[];
    expect(Object.keys(saved[0]).sort()).toEqual(['answer', 'error', 'question']);
    expect(JSON.stringify(saved)).not.toContain('Confidential excerpt');
    expect(service.history()[0].sources).toBeDefined();
  });
});
