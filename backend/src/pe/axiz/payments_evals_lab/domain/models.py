from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class RagStrategy(StrEnum):
    NATIVE = "native"
    HYBRID = "hybrid"
    GRAPHRAG = "graphrag"
    RAGLIGHT = "raglight"
    LIGHTRAG = "lightrag"
    AUTO = "auto"


class TraceStage(StrEnum):
    RECEIVED = "received"
    ROUTING = "routing"
    TOOL = "tool"
    RETRIEVAL = "retrieval"
    GENERATION = "generation"
    EVALUATION = "evaluation"
    COMPLETED = "completed"
    ERROR = "error"


class Transaction(BaseModel):
    transaction_id: str
    merchant_id: str
    amount: float
    currency: str
    status: Literal["approved", "declined", "pending", "reversed"]
    authorization_code: str | None = None
    acquirer: str
    issuer: str
    card_network: str
    created_at: datetime
    masked_pan: str


class AuthorizationCode(BaseModel):
    code: str
    meaning: str
    category: str
    recommended_action: str
    retryable: bool


class RetrievedContext(BaseModel):
    id: str
    source: str
    text: str
    score: float
    raw_score: float | None = None
    rerank_score: float | None = None
    rank: int | None = None
    entities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCallTrace(BaseModel):
    tool: str
    arguments: dict[str, Any]
    schema_valid: bool
    result: Any = None
    error: str | None = None
    latency_ms: float = 0.0
    turn_id: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TraceEvent(BaseModel):
    stage: TraceStage
    label: str
    detail: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)


class ExecutionTrace(BaseModel):
    trace_id: str
    case_id: str | None = None
    session_id: str | None = None
    request_id: str | None = None
    intent: str | None = None
    route: str | None = None
    events: list[TraceEvent] = Field(default_factory=list)
    turns: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    retrieval: dict[str, Any] = Field(default_factory=dict)
    answer: str = ""
    usage: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    session_id: str | None = None
    request_id: str | None = None
    strategy: RagStrategy = RagStrategy.AUTO
    top_k: int = Field(default=5, ge=1, le=10)
    include_case_draft: bool = True


class ChatResponse(BaseModel):
    session_id: str
    request_id: str
    trace_id: str
    answer: str
    selected_strategy: str
    intent: str
    contexts: list[RetrievedContext]
    tools: list[ToolCallTrace]
    timings_ms: dict[str, float]
    usage: dict[str, Any]


class MetricResult(BaseModel):
    metric: str
    framework: str
    dimension: str
    score: float | None = None
    threshold: float | None = None
    passed: bool | None = None
    reason: str = ""
    case_id: str | None = None
    strategy: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    latency_ms: float | None = None
    tokens: int | None = None
    cost: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("score")
    @classmethod
    def finite_score(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("El score debe ser finito")
        return float(value)


class EvalRunRequest(BaseModel):
    suite: str = "full"
    strategy: RagStrategy = RagStrategy.AUTO
    candidate: str = "candidate"
    baseline: str = "baseline"
    prompt_version: str = "v1"
    model: str = "deterministic"
    include_external_judges: bool = False


class EvalRunSummary(BaseModel):
    run_id: str
    suite: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    started_at: datetime
    completed_at: datetime | None = None
    progress: float = 0.0
    metrics: list[MetricResult] = Field(default_factory=list)
    gates_passed: bool | None = None
    gate_failures: list[str] = Field(default_factory=list)
    aggregate: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class CompareRequest(BaseModel):
    run_ids: list[str] = Field(min_length=2, max_length=10)
