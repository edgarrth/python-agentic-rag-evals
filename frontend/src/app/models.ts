export type RagStrategy = 'auto' | 'native' | 'hybrid' | 'graphrag' | 'raglight' | 'lightrag';
export type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
export type Workspace = 'chat' | 'evals' | 'runs';
export type EvalView = 'overview' | 'agent' | 'rag' | 'routing' | 'graph' | 'prompts' | 'safety' | 'conversation' | 'performance' | 'regression' | 'voice' | 'all';

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export interface RetrievedContext {
  id: string;
  source: string;
  text: string;
  score: number;
  raw_score?: number | null;
  rerank_score?: number | null;
  rank?: number | null;
  entities: string[];
  metadata: Record<string, unknown>;
}

export interface ToolCallTrace {
  tool: string;
  arguments: Record<string, unknown>;
  schema_valid: boolean;
  result?: unknown;
  error?: string | null;
  latency_ms: number;
  turn_id?: string | null;
  started_at?: string;
}

export interface ChatRequest {
  question: string;
  session_id?: string | null;
  request_id?: string | null;
  strategy: RagStrategy;
  top_k: number;
  include_case_draft: boolean;
}

export interface ChatResponse {
  session_id: string;
  request_id: string;
  trace_id: string;
  answer: string;
  selected_strategy: string;
  intent: string;
  contexts: RetrievedContext[];
  tools: ToolCallTrace[];
  timings_ms: Record<string, number>;
  usage: Record<string, unknown>;
}

export interface StreamEvent {
  event: string;
  label?: string;
  detail?: string;
  response?: ChatResponse;
  error?: string;
  trace_id?: string;
  progress?: number;
  family?: string;
  status?: string;
  run?: EvalRunSummary;
  [key: string]: unknown;
}

export interface ExecutionStep {
  id: string;
  event: string;
  label: string;
  detail: string;
  status: 'active' | 'done' | 'error';
  timestamp: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
  response?: ChatResponse;
  steps?: ExecutionStep[];
  streaming?: boolean;
  error?: string;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  sessionId?: string;
  messages: ChatMessage[];
}

export interface ConversationGroup {
  label: string;
  conversations: Conversation[];
}

export interface MetricResult {
  metric: string;
  framework: string;
  dimension: string;
  score: number | null;
  threshold: number | null;
  passed: boolean | null;
  reason: string;
  case_id?: string | null;
  strategy?: string | null;
  model?: string | null;
  prompt_version?: string | null;
  latency_ms?: number | null;
  tokens?: number | null;
  cost?: number | null;
  details: Record<string, unknown>;
}

export interface EvalRunRequest {
  suite: string;
  strategy: RagStrategy;
  candidate: string;
  baseline: string;
  prompt_version: string;
  model: string;
  include_external_judges: boolean;
}

export interface EvalRunSummary {
  run_id: string;
  suite: string;
  status: RunStatus;
  started_at: string;
  completed_at?: string | null;
  progress: number;
  metrics: MetricResult[];
  gates_passed?: boolean | null;
  gate_failures: string[];
  aggregate: Record<string, unknown>;
  error?: string | null;
}

export interface EvalRunCreated {
  run_id: string;
  status: RunStatus;
  stream: string;
}

export interface SuiteCatalog {
  suites: Record<string, string[]>;
}

export interface ComparisonResponse {
  runs: string[];
  comparison: Array<Record<string, string | number | null>>;
}

export interface TraceEventModel {
  stage: string;
  label: string;
  detail: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

export interface ExecutionTrace {
  trace_id: string;
  case_id?: string | null;
  session_id?: string | null;
  request_id?: string | null;
  intent?: string | null;
  route?: string | null;
  events: TraceEventModel[];
  turns: Array<Record<string, unknown>>;
  tool_calls: ToolCallTrace[];
  retrieval: Record<string, unknown>;
  answer: string;
  usage: Record<string, unknown>;
  created_at: string;
}
