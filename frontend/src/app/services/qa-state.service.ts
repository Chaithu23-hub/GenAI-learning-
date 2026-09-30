import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { finalize } from 'rxjs';

import { ApiError } from '../core/error.interceptor';
import { HistoryItem } from '../models/types';
import { ApiService } from './api.service';

const STORAGE_KEY = 'legal_rag.chat_history.v1';
const MAX_PERSISTED_ITEMS = 100;

// Persisted state container. History is stored in localStorage so a page
// refresh keeps the conversation; pending items are tagged with a stable
// pendingId so they can be updated even if the list mutates (e.g. reset).
@Injectable({ providedIn: 'root' })
export class QaStateService {
  private readonly api = inject(ApiService);
  private nextPendingId = 1;

  readonly history = signal<HistoryItem[]>(this.loadFromStorage());
  readonly isLoading = signal(false);
  readonly hasHistory = computed(() => this.history().length > 0);

  constructor() {
    effect(() => {
      const snapshot = this.history()
        .filter((item) => !item.isLoading)
        .slice(-MAX_PERSISTED_ITEMS);
      this.saveToStorage(snapshot);
    });
  }

  ask(question: string): void {
    const trimmed = question.trim();
    if (!trimmed) return;

    const pendingId = this.nextPendingId++;
    this.isLoading.set(true);
    this.history.update((h) => [
      ...h,
      { question: trimmed, isLoading: true, pendingId },
    ]);

    this.api
      .ask(trimmed)
      .pipe(finalize(() => this.isLoading.set(false)))
      .subscribe({
        next: (response) => this.mergePending(pendingId, { ...response }),
        error: (err: ApiError | Error) =>
          this.mergePending(pendingId, {
            error:
              err instanceof ApiError
                ? `${err.message}${err.requestId ? ` (request ${err.requestId})` : ''}`
                : 'Failed to reach the legal assistant backend.',
          }),
      });
  }

  reset(): void {
    this.history.set([]);
  }

  private mergePending(pendingId: number, patch: Partial<HistoryItem>): void {
    this.history.update((h) => {
      const idx = h.findIndex((item) => item.pendingId === pendingId);
      // If the user reset the chat mid-flight the item is gone; drop silently.
      if (idx < 0) return h;
      const next = [...h];
      next[idx] = { ...next[idx], ...patch, isLoading: false, pendingId: undefined };
      return next;
    });
  }

  private loadFromStorage(): HistoryItem[] {
    try {
      const raw = globalThis.localStorage?.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw) as unknown;
      if (!Array.isArray(parsed)) return [];
      return parsed
        .filter((item): item is HistoryItem =>
          !!item && typeof (item as HistoryItem).question === 'string')
        .map((item) => ({ ...item, isLoading: false, pendingId: undefined }));
    } catch {
      return [];
    }
  }

  private saveToStorage(items: HistoryItem[]): void {
    try {
      globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(items));
    } catch {
      /* storage full/unavailable — silently skip */
    }
  }
}
