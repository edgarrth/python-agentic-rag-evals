import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import {
  ChatRequest,
  ComparisonResponse,
  EvalRunCreated,
  EvalRunRequest,
  EvalRunSummary,
  ExecutionTrace,
  HealthResponse,
  RuntimeOptions,
  StreamEvent,
  SuiteCatalog
} from '../models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly apiBase = '/api/v1';

  constructor(private readonly http: HttpClient) {}

  health(): Promise<HealthResponse> {
    return firstValueFrom(this.http.get<HealthResponse>('/health'));
  }

  runtimeOptions(): Promise<RuntimeOptions> {
    return firstValueFrom(this.http.get<RuntimeOptions>(`${this.apiBase}/runtime/options`));
  }

  suites(): Promise<SuiteCatalog> {
    return firstValueFrom(this.http.get<SuiteCatalog>(`${this.apiBase}/evals/suites`));
  }

  runs(): Promise<EvalRunSummary[]> {
    return firstValueFrom(this.http.get<EvalRunSummary[]>(`${this.apiBase}/evals/runs`));
  }

  run(runId: string): Promise<EvalRunSummary> {
    return firstValueFrom(this.http.get<EvalRunSummary>(`${this.apiBase}/evals/runs/${encodeURIComponent(runId)}`));
  }

  createRun(request: EvalRunRequest): Promise<EvalRunCreated> {
    return firstValueFrom(this.http.post<EvalRunCreated>(`${this.apiBase}/evals/runs`, request));
  }

  compare(runIds: string[]): Promise<ComparisonResponse> {
    return firstValueFrom(this.http.post<ComparisonResponse>(`${this.apiBase}/evals/compare`, { run_ids: runIds }));
  }

  trace(traceId: string): Promise<ExecutionTrace> {
    return firstValueFrom(this.http.get<ExecutionTrace>(`${this.apiBase}/traces/${encodeURIComponent(traceId)}`));
  }

  async chatStream(request: ChatRequest, onEvent: (event: StreamEvent) => void, signal?: AbortSignal): Promise<void> {
    await this.consumeSse(
      `${this.apiBase}/chat/stream`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request), signal },
      onEvent
    );
  }

  async runStream(runId: string, onEvent: (event: StreamEvent) => void, signal?: AbortSignal): Promise<void> {
    await this.consumeSse(`${this.apiBase}/evals/runs/${encodeURIComponent(runId)}/stream`, { method: 'GET', signal }, onEvent);
  }

  private async consumeSse(url: string, init: RequestInit, onEvent: (event: StreamEvent) => void): Promise<void> {
    const response = await fetch(url, init);
    if (!response.ok || !response.body) {
      throw new Error(`HTTP ${response.status}: no se pudo abrir el stream`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() || '';
      for (const frame of frames) {
        const parsed = this.parseSseFrame(frame);
        if (parsed) onEvent(parsed);
      }
      if (done) break;
    }

    if (buffer.trim()) {
      const parsed = this.parseSseFrame(buffer);
      if (parsed) onEvent(parsed);
    }
  }

  private parseSseFrame(frame: string): StreamEvent | null {
    const lines = frame.split(/\r?\n/);
    let eventName = 'message';
    const data: string[] = [];
    for (const line of lines) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim();
      if (line.startsWith('data:')) data.push(line.slice(5).trim());
    }
    if (!data.length) return null;
    try {
      const payload = JSON.parse(data.join('\n')) as Record<string, unknown>;
      return { event: eventName, ...payload } as StreamEvent;
    } catch {
      return { event: eventName, detail: data.join('\n') };
    }
  }
}
