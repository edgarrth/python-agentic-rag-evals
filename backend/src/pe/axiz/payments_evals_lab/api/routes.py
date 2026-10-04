from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from pe.axiz.payments_evals_lab.domain.models import ChatRequest, CompareRequest, EvalRunRequest, EvalRunSummary, GenerationProvider
from pe.axiz.payments_evals_lab.observability.tracing import trace_store
from pe.axiz.payments_evals_lab.services.container import get_container
from pe.axiz.payments_evals_lab.services.eval_run_store import eval_run_store
from pe.axiz.payments_evals_lab.services.session_store import session_store

router = APIRouter()


def sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


@router.get("/health")
async def health() -> dict:
    container = get_container()
    settings = container.settings
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": "1.3.0",
        "runtime": {
            "generation_provider": settings.generation_provider,
            "generation_model": settings.openai_model if settings.generation_provider == "openai" else "deterministic",
            "embedding_provider": settings.embedding_provider,
            "embedding_model": "hashing",
            "judge_provider": settings.judge_provider,
            "external_judges_enabled": settings.eval_judge_enabled,
        },
    }


@router.get("/api/v1/runtime/options")
async def runtime_options() -> dict:
    container = get_container()
    settings = container.settings
    prompt_versions = container.controller.generator.prompt_versions() if container.controller.generator is not None else ["v1"]
    return {
        "generation_providers": ["deterministic", "openai"],
        "models": {
            "deterministic": ["deterministic"],
            "openai": settings.openai_model_options,
        },
        "judge_models": {
            "deterministic": ["deterministic"],
            "openai": settings.openai_judge_model_options,
        },
        "prompt_versions": prompt_versions,
        "defaults": {
            # Se muestran OpenAI y un Mini por defecto aunque falte la clave; la GUI informa el problema antes de ejecutar.
            # El motor determinista continúa disponible como alternativa explícita.
            "generation_provider": "openai",
            "model": settings.openai_model,
            "prompt_version": prompt_versions[0],
            "judge_provider": "openai",
            "judge_model": settings.openai_judge_model,
        },
        "embedding": {
            "provider": settings.embedding_provider,
            "model": "hashing",
        },
        "external_judges": {
            "enabled_by_env": settings.eval_judge_enabled,
            "openai_key_configured": bool(settings.openai_api_key),
            "deepeval": settings.deepeval_enabled,
            "ragas": settings.ragas_enabled,
        },
    }


@router.post("/api/v1/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    container = get_container()
    queue: asyncio.Queue[dict] = asyncio.Queue()

    async def sink(event: dict) -> None:
        await queue.put(event)

    async def execute() -> None:
        try:
            response = await container.controller.run(request, sink=sink)
            await queue.put({"event": "result", "response": response.model_dump(mode="json")})
        except Exception as exc:  # noqa: BLE001
            await queue.put({"event": "error", "error": f"{type(exc).__name__}: {exc}"})
        finally:
            await queue.put({"event": "eof"})

    asyncio.create_task(execute())

    async def generate() -> AsyncIterator[str]:
        while True:
            item = await queue.get()
            event = item.pop("event")
            if event == "eof":
                yield sse("eof", {"status": "completed"})
                break
            yield sse(event, item)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/api/v1/chat/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return session


@router.get("/api/v1/evals/suites")
async def list_suites() -> dict:
    return {"suites": get_container().eval_runner.suites()}


@router.get("/api/v1/evals/runs")
async def list_runs() -> list[dict]:
    return [item.model_dump(mode="json") for item in eval_run_store.list()]


async def _execute_eval(run: EvalRunSummary, request: EvalRunRequest) -> None:
    container = get_container()
    run.status = "running"
    eval_run_store.update(run)
    await eval_run_store.publish(run.run_id, {"event": "started", "run_id": run.run_id, "suite": run.suite})

    async def progress(event: dict) -> None:
        run.progress = float(event.get("progress", run.progress))
        eval_run_store.update(run)
        await eval_run_store.publish(run.run_id, {"event": "progress", **event})

    try:
        metrics, gates_passed, failures, aggregate = await container.eval_runner.run(
            request.suite,
            request.strategy,
            request.include_external_judges,
            progress=progress,
            generation_provider=request.generation_provider,
            model=request.model,
            prompt_version=request.prompt_version,
            judge_provider=request.judge_provider,
            judge_model=request.judge_model,
            top_k=request.top_k,
        )
        run.metrics = metrics
        run.gates_passed = gates_passed
        run.gate_failures = failures
        run.aggregate = aggregate
        run.progress = 1.0
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        eval_run_store.update(run)
        await eval_run_store.publish(run.run_id, {"event": "completed", "run": run.model_dump(mode="json")})
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"
        run.completed_at = datetime.now(UTC)
        eval_run_store.update(run)
        await eval_run_store.publish(run.run_id, {"event": "failed", "error": run.error})


@router.post("/api/v1/evals/runs", status_code=202)
async def create_run(request: EvalRunRequest) -> dict:
    if request.suite not in get_container().eval_runner.suites():
        raise HTTPException(status_code=422, detail="Suite no soportada")
    config = request.model_dump(mode="json")
    run = eval_run_store.create(request.suite, request_config=config)
    asyncio.create_task(_execute_eval(run, request))
    return {"run_id": run.run_id, "status": run.status, "stream": f"/api/v1/evals/runs/{run.run_id}/stream"}


@router.get("/api/v1/evals/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    run = eval_run_store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run no encontrado")
    return run.model_dump(mode="json")


@router.get("/api/v1/evals/runs/{run_id}/stream")
async def stream_run(run_id: str) -> StreamingResponse:
    run = eval_run_store.get(run_id)
    queue = eval_run_store.queue(run_id)
    if run is None or queue is None:
        raise HTTPException(status_code=404, detail="Run no encontrado")

    async def generate() -> AsyncIterator[str]:
        if run.status in {"completed", "failed", "cancelled"}:
            yield sse("snapshot", {"run": run.model_dump(mode="json")})
            return
        while True:
            item = await queue.get()
            event_name = str(item.get("event", "progress"))
            yield sse(event_name, item)
            if event_name in {"completed", "failed", "cancelled"}:
                break

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/api/v1/evals/compare")
async def compare_runs(request: CompareRequest) -> dict:
    runs = []
    for run_id in request.run_ids:
        run = eval_run_store.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run no encontrado: {run_id}")
        runs.append(run)
    metrics = sorted({metric.metric for run in runs for metric in run.metrics})
    comparison = []
    for name in metrics:
        row = {"metric": name}
        for run in runs:
            values = [item.score for item in run.metrics if item.metric == name and item.score is not None]
            row[run.run_id] = sum(values) / len(values) if values else None
        comparison.append(row)
    return {"runs": [run.run_id for run in runs], "comparison": comparison}


@router.get("/api/v1/traces/{trace_id}")
async def get_trace(trace_id: str) -> dict:
    trace = trace_store.get(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Traza no encontrada")
    return trace.model_dump(mode="json")


class PromptEvalRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=4000)
    strategy: str = "auto"
    generation_provider: GenerationProvider = GenerationProvider.DETERMINISTIC
    model: str = "deterministic"
    prompt_version: str = "v1"


@router.post("/api/v1/evals/prompt")
async def prompt_eval(request: PromptEvalRequest) -> dict:
    from pe.axiz.payments_evals_lab.domain.models import RagStrategy

    try:
        strategy = RagStrategy(request.strategy)
    except ValueError:
        strategy = RagStrategy.AUTO
    response = await get_container().controller.run(
        ChatRequest(
            question=request.prompt,
            strategy=strategy,
            include_case_draft=False,
            generation_provider=request.generation_provider,
            model=request.model,
            prompt_version=request.prompt_version,
        )
    )
    return {
        "output": response.answer,
        "trace_id": response.trace_id,
        "strategy": response.selected_strategy,
        "intent": response.intent,
        "generation_provider": response.generation_provider,
        "model": response.model,
        "prompt_version": response.prompt_version,
    }
