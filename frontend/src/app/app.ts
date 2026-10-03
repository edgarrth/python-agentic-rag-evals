import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  HostListener,
  OnInit,
  ViewChild,
  computed,
  signal
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from './services/api.service';
import {
  ChatMessage,
  ChatResponse,
  ComparisonResponse,
  Conversation,
  ConversationGroup,
  EvalRunSummary,
  EvalView,
  GenerationProvider,
  ExecutionStep,
  ExecutionTrace,
  MetricResult,
  RagStrategy,
  RuntimeOptions,
  StreamEvent,
  Workspace
} from './models';

interface EvalTab {
  id: EvalView;
  label: string;
  dimensions: string[];
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.css',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class AppComponent implements OnInit {
  readonly Math = Math;
  @ViewChild('chatScroll') private chatScroll?: ElementRef<HTMLElement>;

  private readonly storageKey = 'axiz-payments-agentic-evals-conversations-v2';
  private chatAbort?: AbortController;
  private runAbort?: AbortController;
  private followStream = true;
  private benchmarkAbort?: AbortController;

  readonly strategies: Array<{ value: RagStrategy; label: string }> = [
    { value: 'auto', label: 'Adaptive Routing' },
    { value: 'native', label: 'Native RAG' },
    { value: 'hybrid', label: 'Hybrid RAG' },
    { value: 'graphrag', label: 'GraphRAG' },
    { value: 'raglight', label: 'RAGLight' },
    { value: 'lightrag', label: 'LightRAG' }
  ];


  readonly benchmarkStrategyOptions: Array<{ value: RagStrategy; label: string }> = this.strategies.filter((item) => item.value !== 'auto');
  readonly providerOptions: Array<{ value: GenerationProvider; label: string; help: string }> = [
    { value: 'deterministic', label: 'Determinista (sin LLM externo)', help: 'Sin LLM externo; salida reproducible basada en reglas y evidencia.' },
    { value: 'openai', label: 'OpenAI Responses API', help: 'Generación real mediante OpenAI Responses API con el modelo seleccionado.' }
  ];

  readonly examples = [
    'Analiza TX-1007, explica el rechazo y genera un borrador de caso si corresponde.',
    '¿Qué significa el código de autorización 05 y qué acción operativa corresponde?',
    '¿Cómo evita la idempotencia cobros duplicados cuando ocurre un timeout?',
    'Explica la relación entre autorización, adquirente, emisor y conciliación.'
  ];

  readonly evalTabs: EvalTab[] = [
    { id: 'overview', label: 'Overview', dimensions: [] },
    { id: 'agent', label: 'Agent', dimensions: ['agentic'] },
    { id: 'rag', label: 'RAG', dimensions: ['retrieval', 'rag_retrieval', 'rag_generation'] },
    { id: 'routing', label: 'Routing', dimensions: ['routing'] },
    { id: 'graph', label: 'Graph / Entities', dimensions: ['graph'] },
    { id: 'prompts', label: 'Prompts', dimensions: ['prompt'] },
    { id: 'safety', label: 'Safety & Red Team', dimensions: ['safety', 'adversarial'] },
    { id: 'conversation', label: 'Conversación', dimensions: ['conversation', 'robustness'] },
    { id: 'performance', label: 'Performance & Cost', dimensions: ['performance'] },
    { id: 'regression', label: 'Regression & Drift', dimensions: ['regression', 'drift', 'uncertainty'] },
    { id: 'voice', label: 'Voice', dimensions: ['voice_stt', 'voice_tts', 'voice_performance', 'voice_conversation'] },
    { id: 'all', label: 'Todas', dimensions: [] }
  ];

  workspace = signal<Workspace>('chat');
  sidebarOpen = signal(false);
  apiStatus = signal<'checking' | 'online' | 'offline'>('checking');
  apiVersion = signal('');
  notice = signal('');
  errorMessage = signal('');

  runtimeOptions = signal<RuntimeOptions | null>(null);
  conversations = signal<Conversation[]>([]);
  activeConversationId = signal('');
  question = '';
  strategy: RagStrategy = 'auto';
  topK = 5;
  includeCaseDraft = true;
  chatGenerationProvider: GenerationProvider = 'deterministic';
  chatModelName = 'deterministic';
  chatPromptVersion = 'v1';
  chatLoading = signal(false);
  showJumpToLatest = signal(false);

  suiteCatalog = signal<Record<string, string[]>>({});
  selectedSuite = 'full';
  evalStrategy: RagStrategy = 'auto';
  evalTopK = 5;
  evalGenerationProvider: GenerationProvider = 'deterministic';
  includeExternalJudges = false;
  promptVersion = 'v1';
  modelName = 'deterministic';
  judgeProvider: GenerationProvider = 'deterministic';
  judgeModelName = 'deterministic';
  evalLoading = signal(false);
  evalProgress = signal(0);
  evalFamily = signal('');
  currentRun = signal<EvalRunSummary | null>(null);
  runs = signal<EvalRunSummary[]>([]);
  evalView = signal<EvalView>('overview');
  metricSearch = '';
  metricStatus: 'all' | 'passed' | 'failed' | 'info' = 'all';
  compareSelection = signal<string[]>([]);
  comparison = signal<ComparisonResponse | null>(null);
  comparisonLoading = signal(false);
  benchmarkSelection = signal<RagStrategy[]>(['native', 'hybrid', 'graphrag', 'raglight', 'lightrag']);
  benchmarkLoading = signal(false);
  benchmarkProgress = signal(0);
  benchmarkRuns = signal<EvalRunSummary[]>([]);
  benchmarkComparison = signal<ComparisonResponse | null>(null);

  selectedTrace = signal<ExecutionTrace | null>(null);
  traceLoading = signal(false);

  readonly activeConversation = computed(() =>
    this.conversations().find((item) => item.id === this.activeConversationId())
  );

  readonly messages = computed(() => this.activeConversation()?.messages || []);

  readonly pageTitle = computed(() => {
    if (this.workspace() === 'evals') return 'Laboratorio de Evals';
    if (this.workspace() === 'runs') return 'Historial y comparación';
    return this.activeConversation()?.title || 'Agente de Payment Processing';
  });

  readonly runStats = computed(() => this.calculateRunStats(this.currentRun()));

  constructor(private readonly api: ApiService) {}

  async ngOnInit(): Promise<void> {
    this.restoreConversations();
    if (!this.activeConversationId()) this.newConversation();
    await Promise.allSettled([this.checkHealth(), this.loadRuntimeOptions(), this.loadSuites(), this.refreshRuns()]);
  }

  conversationGroups(): ConversationGroup[] {
    const now = new Date();
    const groups = new Map<string, Conversation[]>();
    const order = ['Hoy', 'Ayer', 'Últimos 7 días', 'Últimos 30 días', 'Anteriores'];
    for (const item of [...this.conversations()].sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt))) {
      const label = this.conversationGroupLabel(new Date(item.updatedAt), now);
      groups.set(label, [...(groups.get(label) || []), item]);
    }
    return order.filter((label) => groups.has(label)).map((label) => ({ label, conversations: groups.get(label) || [] }));
  }

  switchWorkspace(workspace: Workspace): void {
    this.workspace.set(workspace);
    this.sidebarOpen.set(false);
    this.notice.set('');
    this.errorMessage.set('');
    if (workspace === 'runs') void this.refreshRuns();
    if (workspace === 'evals' && !Object.keys(this.suiteCatalog()).length) void this.loadSuites();
    if (workspace === 'chat') setTimeout(() => this.focusComposer(), 0);
  }

  toggleSidebar(): void {
    this.sidebarOpen.update((value) => !value);
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.selectedTrace()) {
      this.closeTrace();
      return;
    }
    if (this.sidebarOpen()) this.sidebarOpen.set(false);
  }

  async checkHealth(): Promise<void> {
    this.apiStatus.set('checking');
    try {
      const result = await this.api.health();
      this.apiStatus.set(result.status === 'ok' ? 'online' : 'offline');
      this.apiVersion.set(result.version);
    } catch {
      this.apiStatus.set('offline');
    }
  }


  async loadRuntimeOptions(): Promise<void> {
    try {
      const options = await this.api.runtimeOptions();
      this.runtimeOptions.set(options);
      this.chatGenerationProvider = options.defaults.generation_provider;
      this.chatModelName = options.defaults.model;
      this.chatPromptVersion = options.defaults.prompt_version;
      this.evalGenerationProvider = options.defaults.generation_provider;
      this.modelName = options.defaults.model;
      this.promptVersion = options.defaults.prompt_version;
      this.judgeProvider = options.defaults.judge_provider;
      this.judgeModelName = options.defaults.judge_model;
      this.normalizeModels();
    } catch (error) {
      this.errorMessage.set(this.errorText(error));
    }
  }

  modelOptions(provider: GenerationProvider): string[] {
    return this.runtimeOptions()?.models?.[provider] || (provider === 'deterministic' ? ['deterministic'] : []);
  }

  promptVersions(): string[] {
    return this.runtimeOptions()?.prompt_versions || ['v1'];
  }

  onChatProviderChange(): void {
    this.chatModelName = this.defaultModel(this.chatGenerationProvider);
  }

  onEvalProviderChange(): void {
    this.modelName = this.defaultModel(this.evalGenerationProvider);
  }

  onJudgeProviderChange(): void {
    this.judgeModelName = this.defaultModel(this.judgeProvider);
  }

  providerLabel(provider: string | null | undefined): string {
    if (provider === 'openai') return 'OpenAI';
    if (provider === 'deterministic') return 'Determinista';
    return provider || '—';
  }

  currentChatRuntimeLabel(): string {
    return this.chatGenerationProvider === 'openai'
      ? `OpenAI · ${this.chatModelName} · ${this.chatPromptVersion}`
      : `Determinista · sin LLM externo · ${this.chatPromptVersion}`;
  }

  currentEvalRuntimeLabel(): string {
    const sut = this.evalGenerationProvider === 'openai' ? `OpenAI · ${this.modelName}` : 'Determinista';
    const judge = this.includeExternalJudges
      ? `${this.providerLabel(this.judgeProvider)} · ${this.judgeModelName}`
      : 'Determinista / reglas';
    return `SUT: ${sut} · Judge: ${judge} · Prompt: ${this.promptVersion}`;
  }

  useExample(example: string): void {
    this.switchWorkspace('chat');
    this.question = example;
    setTimeout(() => this.focusComposer(), 0);
  }

  newConversation(): void {
    if (this.chatLoading()) return;
    const now = new Date().toISOString();
    const conversation: Conversation = {
      id: crypto.randomUUID(),
      title: 'Nueva conversación',
      createdAt: now,
      updatedAt: now,
      messages: []
    };
    this.conversations.update((items) => [conversation, ...items]);
    this.activeConversationId.set(conversation.id);
    this.workspace.set('chat');
    this.question = '';
    this.persistConversations();
    setTimeout(() => this.focusComposer(), 0);
  }

  openConversation(id: string): void {
    if (this.chatLoading()) return;
    this.activeConversationId.set(id);
    this.workspace.set('chat');
    this.sidebarOpen.set(false);
    setTimeout(() => this.scrollToLatest(true), 0);
  }

  deleteConversation(event: Event, id: string): void {
    event.stopPropagation();
    const target = this.conversations().find((item) => item.id === id);
    if (!target) return;
    if (!confirm(`¿Eliminar la conversación “${target.title}”?`)) return;
    this.conversations.update((items) => items.filter((item) => item.id !== id));
    if (this.activeConversationId() === id) {
      const next = this.conversations()[0];
      if (next) this.activeConversationId.set(next.id);
      else this.newConversation();
    }
    this.persistConversations();
  }

  onComposerKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void this.send();
    }
  }

  async send(): Promise<void> {
    const text = this.question.trim();
    if (!text || this.chatLoading()) return;
    if (!this.activeConversation()) this.newConversation();

    this.question = '';
    this.errorMessage.set('');
    this.chatLoading.set(true);
    this.followStream = true;
    this.showJumpToLatest.set(false);

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      createdAt: new Date().toISOString()
    };
    const assistantId = crypto.randomUUID();
    const assistant: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      createdAt: new Date().toISOString(),
      streaming: true,
      steps: []
    };
    this.appendMessages([userMessage, assistant]);
    this.updateConversationTitle(text);
    this.scrollToLatest(true);

    const controller = new AbortController();
    this.chatAbort = controller;
    const conversation = this.activeConversation();

    try {
      await this.api.chatStream(
        {
          question: text,
          session_id: conversation?.sessionId || null,
          request_id: crypto.randomUUID(),
          strategy: this.strategy,
          top_k: this.topK,
          include_case_draft: this.includeCaseDraft,
          generation_provider: this.chatGenerationProvider,
          model: this.chatModelName,
          prompt_version: this.chatPromptVersion
        },
        (event) => this.handleChatEvent(assistantId, event),
        controller.signal
      );
    } catch (error) {
      if (controller.signal.aborted) {
        this.patchMessage(assistantId, {
          streaming: false,
          error: 'La ejecución se detuvo desde la interfaz.',
          content: 'Ejecución detenida antes de recibir el resultado final.'
        });
      } else {
        const message = this.errorText(error);
        this.patchMessage(assistantId, { streaming: false, error: message, content: 'No se pudo completar la consulta.' });
        this.errorMessage.set(message);
      }
    } finally {
      this.chatLoading.set(false);
      this.chatAbort = undefined;
      this.markLastStepDone(assistantId);
      this.persistConversations();
      this.scrollToLatest();
      setTimeout(() => this.focusComposer(), 0);
    }
  }

  stopChat(): void {
    this.chatAbort?.abort();
  }

  retryLastQuestion(): void {
    const last = [...this.messages()].reverse().find((item) => item.role === 'user');
    if (!last || this.chatLoading()) return;
    this.question = last.content;
    void this.send();
  }

  onChatScroll(): void {
    const element = this.chatScroll?.nativeElement;
    if (!element) return;
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight;
    this.followStream = distance < 140;
    this.showJumpToLatest.set(!this.followStream && this.chatLoading());
  }

  scrollToLatest(force = false): void {
    if (!force && !this.followStream) {
      this.showJumpToLatest.set(true);
      return;
    }
    setTimeout(() => {
      const element = this.chatScroll?.nativeElement;
      if (element) element.scrollTo({ top: element.scrollHeight, behavior: force ? 'auto' : 'smooth' });
      this.followStream = true;
      this.showJumpToLatest.set(false);
    }, 0);
  }

  async inspectTrace(traceId: string): Promise<void> {
    this.traceLoading.set(true);
    try {
      this.selectedTrace.set(await this.api.trace(traceId));
    } catch (error) {
      this.errorMessage.set(this.errorText(error));
    } finally {
      this.traceLoading.set(false);
    }
  }

  closeTrace(): void {
    this.selectedTrace.set(null);
  }

  async copyText(text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      this.notice.set('Contenido copiado al portapapeles.');
      setTimeout(() => this.notice.set(''), 1800);
    } catch {
      this.notice.set('No fue posible copiar automáticamente.');
    }
  }

  async loadSuites(): Promise<void> {
    try {
      const result = await this.api.suites();
      this.suiteCatalog.set(result.suites);
      if (!result.suites[this.selectedSuite]) this.selectedSuite = Object.keys(result.suites)[0] || 'full';
    } catch (error) {
      this.errorMessage.set(this.errorText(error));
    }
  }

  async runEvaluation(): Promise<void> {
    if (this.evalLoading()) return;
    this.evalLoading.set(true);
    this.evalProgress.set(0);
    this.evalFamily.set('Preparando suite');
    this.errorMessage.set('');
    this.comparison.set(null);
    const controller = new AbortController();
    this.runAbort = controller;

    try {
      const created = await this.api.createRun({
        suite: this.selectedSuite,
        strategy: this.evalStrategy,
        candidate: 'candidate',
        baseline: 'baseline',
        prompt_version: this.promptVersion || 'v1',
        generation_provider: this.evalGenerationProvider,
        model: this.modelName || 'deterministic',
        judge_provider: this.includeExternalJudges ? this.judgeProvider : 'deterministic',
        judge_model: this.includeExternalJudges ? this.judgeModelName : 'deterministic',
        top_k: this.evalTopK,
        include_external_judges: this.includeExternalJudges
      });
      this.currentRun.set({
        run_id: created.run_id,
        suite: this.selectedSuite,
        status: created.status,
        started_at: new Date().toISOString(),
        progress: 0,
        metrics: [],
        gate_failures: [],
        aggregate: {},
        request_config: {
          strategy: this.evalStrategy,
          generation_provider: this.evalGenerationProvider,
          model: this.modelName,
          prompt_version: this.promptVersion,
          judge_provider: this.includeExternalJudges ? this.judgeProvider : 'deterministic',
          judge_model: this.includeExternalJudges ? this.judgeModelName : 'deterministic',
          top_k: this.evalTopK
        }
      });

      await this.api.runStream(created.run_id, (event) => this.handleRunEvent(event), controller.signal);
      const finalRun = await this.api.run(created.run_id);
      this.currentRun.set(finalRun);
      this.evalProgress.set(finalRun.progress || 1);
      this.evalFamily.set(finalRun.status === 'completed' ? 'Suite completada' : finalRun.status);
      await this.refreshRuns();
    } catch (error) {
      if (controller.signal.aborted) {
        this.evalFamily.set('Seguimiento detenido');
        this.notice.set('Se detuvo el seguimiento SSE. La ejecución del backend puede continuar.');
      } else {
        this.errorMessage.set(this.errorText(error));
        this.evalFamily.set('Error de ejecución');
      }
    } finally {
      this.evalLoading.set(false);
      this.runAbort = undefined;
    }
  }


  toggleBenchmarkStrategy(strategy: RagStrategy, checked: boolean): void {
    const current = this.benchmarkSelection();
    if (checked && !current.includes(strategy)) this.benchmarkSelection.set([...current, strategy]);
    if (!checked) this.benchmarkSelection.set(current.filter((item) => item !== strategy));
  }

  isBenchmarkSelected(strategy: RagStrategy): boolean {
    return this.benchmarkSelection().includes(strategy);
  }

  async runRagBenchmark(): Promise<void> {
    const selected = this.benchmarkSelection().filter((item) => item !== 'auto');
    if (!selected.length || this.benchmarkLoading()) return;
    this.benchmarkLoading.set(true);
    this.benchmarkProgress.set(0);
    this.benchmarkRuns.set([]);
    this.benchmarkComparison.set(null);
    this.errorMessage.set('');
    const controller = new AbortController();
    this.benchmarkAbort = controller;
    try {
      const completed: EvalRunSummary[] = [];
      for (let index = 0; index < selected.length; index += 1) {
        const ragStrategy = selected[index];
        const created = await this.api.createRun({
          suite: 'rag',
          strategy: ragStrategy,
          candidate: 'benchmark-candidate',
          baseline: 'benchmark-baseline',
          prompt_version: this.promptVersion || 'v1',
          generation_provider: this.evalGenerationProvider,
          model: this.modelName || 'deterministic',
          judge_provider: this.includeExternalJudges ? this.judgeProvider : 'deterministic',
          judge_model: this.includeExternalJudges ? this.judgeModelName : 'deterministic',
          top_k: this.evalTopK,
          include_external_judges: this.includeExternalJudges
        });
        await this.api.runStream(created.run_id, () => undefined, controller.signal);
        const run = await this.api.run(created.run_id);
        completed.push(run);
        this.benchmarkRuns.set([...completed]);
        this.benchmarkProgress.set((index + 1) / selected.length);
      }
      const ids = completed.map((run) => run.run_id);
      if (ids.length >= 2) this.benchmarkComparison.set(await this.api.compare(ids));
      this.compareSelection.set(ids);
      await this.refreshRuns();
      this.notice.set(`Benchmark RAG completado para ${completed.length} estrategias con el mismo Golden Dataset y configuración.`);
    } catch (error) {
      if (controller.signal.aborted) this.notice.set('Benchmark detenido desde la interfaz.');
      else this.errorMessage.set(this.errorText(error));
    } finally {
      this.benchmarkLoading.set(false);
      this.benchmarkAbort = undefined;
    }
  }

  stopBenchmark(): void {
    this.benchmarkAbort?.abort();
  }

  benchmarkRows(): Array<Record<string, string | number | null>> {
    const wanted = new Set(['mrr', 'ndcg@5', 'precision@5', 'recall@5', 'context_precision', 'context_recall', 'context_relevancy', 'faithfulness', 'groundedness', 'answer_relevancy', 'correctness', 'hallucination']);
    return (this.benchmarkComparison()?.comparison || []).filter((row) => wanted.has(String(row['metric'])));
  }

  benchmarkRunLabel(runId: string): string {
    const run = this.benchmarkRuns().find((item) => item.run_id === runId) || this.runs().find((item) => item.run_id === runId);
    return String(run?.request_config?.['strategy'] || runId.slice(0, 8));
  }

  benchmarkQuality(run: EvalRunSummary): number {
    const scored = run.metrics.filter((item) => item.score !== null && item.dimension !== 'integration');
    return scored.length ? scored.reduce((sum, item) => sum + (item.score || 0), 0) / scored.length : 0;
  }

  benchmarkLatency(run: EvalRunSummary): number {
    const values = run.metrics.map((item) => item.latency_ms).filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
  }

  benchmarkBestQuality(): string {
    return this.bestBenchmarkRun((run) => this.benchmarkQuality(run), false);
  }

  benchmarkBestRecall(): string {
    const comparison = this.benchmarkComparison();
    if (!comparison) return '—';
    const row = comparison.comparison.find((item) => item['metric'] === 'context_recall');
    return row ? this.bestRunFromComparisonRow(row, false) : '—';
  }

  benchmarkBestLatency(): string {
    return this.bestBenchmarkRun((run) => this.benchmarkLatency(run), true);
  }

  benchmarkBestBalance(): string {
    const runs = this.benchmarkRuns();
    if (!runs.length) return '—';
    const maxLatency = Math.max(...runs.map((run) => this.benchmarkLatency(run)), 1);
    const ranked = runs.map((run) => ({
      run,
      score: this.benchmarkQuality(run) - (this.benchmarkLatency(run) / maxLatency) * 0.10
    })).sort((a, b) => b.score - a.score);
    return this.benchmarkRunLabel(ranked[0].run.run_id);
  }

  stopRunMonitoring(): void {
    this.runAbort?.abort();
  }

  async refreshRuns(): Promise<void> {
    try {
      const rows = await this.api.runs();
      this.runs.set([...rows].sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at)));
    } catch (error) {
      this.errorMessage.set(this.errorText(error));
    }
  }

  async openRun(runId: string): Promise<void> {
    try {
      this.currentRun.set(await this.api.run(runId));
      this.workspace.set('evals');
      this.evalView.set('overview');
      this.sidebarOpen.set(false);
    } catch (error) {
      this.errorMessage.set(this.errorText(error));
    }
  }

  setEvalView(view: EvalView): void {
    this.evalView.set(view);
  }

  visibleMetrics(): MetricResult[] {
    const run = this.currentRun();
    if (!run) return [];
    const tab = this.evalTabs.find((item) => item.id === this.evalView());
    let rows = run.metrics;
    if (this.evalView() !== 'overview' && this.evalView() !== 'all' && tab?.dimensions.length) {
      rows = rows.filter((metric) => tab.dimensions.includes(metric.dimension));
    }
    const search = this.metricSearch.trim().toLocaleLowerCase();
    if (search) {
      rows = rows.filter((metric) =>
        [metric.metric, metric.dimension, metric.framework, metric.case_id || '', metric.reason || '']
          .join(' ')
          .toLocaleLowerCase()
          .includes(search)
      );
    }
    if (this.metricStatus === 'passed') rows = rows.filter((metric) => metric.passed === true);
    if (this.metricStatus === 'failed') rows = rows.filter((metric) => metric.passed === false);
    if (this.metricStatus === 'info') rows = rows.filter((metric) => metric.passed === null);
    return rows;
  }

  dimensionCards(): Array<{ dimension: string; label: string; score: number; total: number; passed: number; failed: number }> {
    const run = this.currentRun();
    if (!run) return [];
    const groups = new Map<string, MetricResult[]>();
    for (const metric of run.metrics) groups.set(metric.dimension, [...(groups.get(metric.dimension) || []), metric]);
    return [...groups.entries()]
      .map(([dimension, rows]) => {
        const scored = rows.filter((item) => item.score !== null);
        return {
          dimension,
          label: this.humanize(dimension),
          score: scored.length ? scored.reduce((sum, item) => sum + (item.score || 0), 0) / scored.length : 0,
          total: rows.length,
          passed: rows.filter((item) => item.passed === true).length,
          failed: rows.filter((item) => item.passed === false).length
        };
      })
      .sort((a, b) => a.label.localeCompare(b.label));
  }

  toggleRunSelection(runId: string, checked: boolean): void {
    const current = this.compareSelection();
    if (checked && !current.includes(runId) && current.length < 10) this.compareSelection.set([...current, runId]);
    if (!checked) this.compareSelection.set(current.filter((id) => id !== runId));
  }

  isRunSelected(runId: string): boolean {
    return this.compareSelection().includes(runId);
  }

  async compareRuns(): Promise<void> {
    const ids = this.compareSelection();
    if (ids.length < 2) return;
    this.comparisonLoading.set(true);
    try {
      this.comparison.set(await this.api.compare(ids));
    } catch (error) {
      this.errorMessage.set(this.errorText(error));
    } finally {
      this.comparisonLoading.set(false);
    }
  }

  scorePercent(metric: MetricResult): number {
    return Math.max(0, Math.min(100, Math.round((metric.score || 0) * 100)));
  }

  scoreText(score: number | null | undefined): string {
    return score === null || score === undefined ? 'N/A' : `${(score * 100).toFixed(1)}%`;
  }

  passLabel(value: boolean | null | undefined): string {
    if (value === true) return 'Pass';
    if (value === false) return 'Fail';
    return 'Info';
  }

  statusLabel(status: string): string {
    const labels: Record<string, string> = {
      queued: 'En cola', running: 'Ejecutando', completed: 'Completado', failed: 'Fallido', cancelled: 'Cancelado'
    };
    return labels[status] || status;
  }

  humanize(value: string): string {
    return value
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (letter) => letter.toUpperCase())
      .replace('Rag ', 'RAG ')
      .replace('Ood', 'OOD')
      .replace('Pii', 'PII')
      .replace('Ttfc', 'TTFC')
      .replace('Rtf', 'RTF')
      .replace('Wer', 'WER');
  }

  formatDate(value: string | null | undefined): string {
    if (!value) return '—';
    return new Intl.DateTimeFormat('es-PE', { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(value));
  }

  formatMs(value: number | null | undefined): string {
    if (value === null || value === undefined) return '—';
    return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value.toFixed(0)} ms`;
  }

  objectKeys(value: Record<string, unknown> | null | undefined): string[] {
    return Object.keys(value || {});
  }

  private defaultModel(provider: GenerationProvider): string {
    return this.modelOptions(provider)[0] || (provider === 'deterministic' ? 'deterministic' : '');
  }

  private normalizeModels(): void {
    if (!this.modelOptions(this.chatGenerationProvider).includes(this.chatModelName)) this.chatModelName = this.defaultModel(this.chatGenerationProvider);
    if (!this.modelOptions(this.evalGenerationProvider).includes(this.modelName)) this.modelName = this.defaultModel(this.evalGenerationProvider);
    if (!this.modelOptions(this.judgeProvider).includes(this.judgeModelName)) this.judgeModelName = this.defaultModel(this.judgeProvider);
  }

  private bestBenchmarkRun(selector: (run: EvalRunSummary) => number, lowerIsBetter: boolean): string {
    const runs = this.benchmarkRuns().filter((run) => Number.isFinite(selector(run)));
    if (!runs.length) return '—';
    const ranked = [...runs].sort((a, b) => lowerIsBetter ? selector(a) - selector(b) : selector(b) - selector(a));
    return this.benchmarkRunLabel(ranked[0].run_id);
  }

  private bestRunFromComparisonRow(row: Record<string, string | number | null>, lowerIsBetter: boolean): string {
    const values = (this.benchmarkComparison()?.runs || [])
      .map((runId) => ({ runId, value: row[runId] }))
      .filter((item): item is { runId: string; value: number } => typeof item.value === 'number');
    if (!values.length) return '—';
    values.sort((a, b) => lowerIsBetter ? a.value - b.value : b.value - a.value);
    return this.benchmarkRunLabel(values[0].runId);
  }

  private handleChatEvent(messageId: string, event: StreamEvent): void {
    if (event.event === 'result' && event.response) {
      const response = event.response;
      this.patchMessage(messageId, { content: response.answer, response, streaming: false });
      this.updateActiveConversation((conversation) => ({ ...conversation, sessionId: response.session_id }));
      this.markLastStepDone(messageId);
      this.persistConversations();
      this.scrollToLatest();
      return;
    }
    if (event.event === 'error') {
      this.addExecutionStep(messageId, event.event, event.label || 'Error', event.error || event.detail || 'Error del stream', 'error');
      return;
    }
    if (event.event === 'eof') return;
    this.addExecutionStep(messageId, event.event, event.label || this.humanize(event.event), event.detail || '', 'active');
  }

  private handleRunEvent(event: StreamEvent): void {
    if (typeof event.progress === 'number') this.evalProgress.set(event.progress);
    if (event.family) this.evalFamily.set(`${this.humanize(event.family)} · ${event.status || 'ejecutando'}`);
    if (event.run) {
      this.currentRun.set(event.run);
      this.evalProgress.set(event.run.progress || 1);
    }
    if (event.event === 'failed' && event.error) this.errorMessage.set(event.error);
  }

  private addExecutionStep(messageId: string, event: string, label: string, detail: string, status: ExecutionStep['status']): void {
    this.updateActiveConversation((conversation) => ({
      ...conversation,
      messages: conversation.messages.map((message) => {
        if (message.id !== messageId) return message;
        const steps = [...(message.steps || [])].map((step) => step.status === 'active' ? { ...step, status: 'done' as const } : step);
        steps.push({ id: crypto.randomUUID(), event, label, detail, status, timestamp: new Date().toISOString() });
        return { ...message, steps };
      })
    }));
    this.scrollToLatest();
  }

  private markLastStepDone(messageId: string): void {
    this.updateActiveConversation((conversation) => ({
      ...conversation,
      messages: conversation.messages.map((message) => {
        if (message.id !== messageId) return message;
        return { ...message, steps: (message.steps || []).map((step) => step.status === 'active' ? { ...step, status: 'done' as const } : step) };
      })
    }));
  }

  private appendMessages(messages: ChatMessage[]): void {
    this.updateActiveConversation((conversation) => ({
      ...conversation,
      updatedAt: new Date().toISOString(),
      messages: [...conversation.messages, ...messages]
    }));
    this.persistConversations();
  }

  private patchMessage(messageId: string, patch: Partial<ChatMessage>): void {
    this.updateActiveConversation((conversation) => ({
      ...conversation,
      updatedAt: new Date().toISOString(),
      messages: conversation.messages.map((message) => message.id === messageId ? { ...message, ...patch } : message)
    }));
  }

  private updateConversationTitle(text: string): void {
    const conversation = this.activeConversation();
    if (!conversation || conversation.title !== 'Nueva conversación') return;
    const clean = text.replace(/\s+/g, ' ').trim();
    const title = clean.length > 52 ? `${clean.slice(0, 49).trim()}...` : clean;
    this.updateActiveConversation((item) => ({ ...item, title }));
  }

  private updateActiveConversation(mapper: (conversation: Conversation) => Conversation): void {
    const id = this.activeConversationId();
    this.conversations.update((items) => items.map((item) => item.id === id ? mapper(item) : item));
  }

  private calculateRunStats(run: EvalRunSummary | null): { total: number; passed: number; failed: number; info: number; passRate: number; score: number } {
    if (!run) return { total: 0, passed: 0, failed: 0, info: 0, passRate: 0, score: 0 };
    const total = run.metrics.length;
    const passed = run.metrics.filter((metric) => metric.passed === true).length;
    const failed = run.metrics.filter((metric) => metric.passed === false).length;
    const info = total - passed - failed;
    const decisions = passed + failed;
    const scores = run.metrics.filter((metric) => metric.score !== null).map((metric) => metric.score as number);
    return {
      total,
      passed,
      failed,
      info,
      passRate: decisions ? passed / decisions : 0,
      score: scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : 0
    };
  }

  private restoreConversations(): void {
    try {
      const raw = localStorage.getItem(this.storageKey);
      const parsed = raw ? JSON.parse(raw) as Conversation[] : [];
      this.conversations.set(Array.isArray(parsed) ? parsed : []);
      if (parsed.length) this.activeConversationId.set(parsed[0].id);
    } catch {
      this.conversations.set([]);
    }
  }

  private persistConversations(): void {
    try {
      const trimmed = this.conversations().slice(0, 25).map((conversation) => ({
        ...conversation,
        messages: conversation.messages.slice(-40)
      }));
      localStorage.setItem(this.storageKey, JSON.stringify(trimmed));
    } catch {
      // El almacenamiento local es opcional para la experiencia de la PoC.
    }
  }

  private conversationGroupLabel(date: Date, now: Date): string {
    const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
    const days = Math.floor((startToday - startDate) / 86400000);
    if (days <= 0) return 'Hoy';
    if (days === 1) return 'Ayer';
    if (days <= 7) return 'Últimos 7 días';
    if (days <= 30) return 'Últimos 30 días';
    return 'Anteriores';
  }

  private focusComposer(): void {
    document.getElementById('chat-composer')?.focus();
  }

  private errorText(error: unknown): string {
    if (error instanceof Error) return error.message;
    return 'Se produjo un error inesperado.';
  }
}
