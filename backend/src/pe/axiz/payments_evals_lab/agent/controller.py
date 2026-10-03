from __future__ import annotations

import re
import time
from typing import Awaitable, Callable
from uuid import uuid4

from pe.axiz.payments_evals_lab.domain.models import ChatRequest, ChatResponse, RagStrategy, TraceStage
from pe.axiz.payments_evals_lab.observability.tracing import TraceStore
from pe.axiz.payments_evals_lab.rag.router import AdaptiveRouter
from pe.axiz.payments_evals_lab.rag.service import RagService
from pe.axiz.payments_evals_lab.services.generation import GenerationService
from pe.axiz.payments_evals_lab.services.session_store import SessionStore
from pe.axiz.payments_evals_lab.tools.registry import ToolRegistry


EventSink = Callable[[dict], Awaitable[None]]
_TX = re.compile(r"\bTX-[0-9]{4}\b", re.I)
_CODE = re.compile(r"\b(?:c[oó]digo\s*)?([0-9]{2,3})\b", re.I)


class AgenticController:
    """Controlador agentic pequeño, trazable y diseñado para evaluación reproducible."""

    def __init__(
        self,
        router: AdaptiveRouter,
        registry: ToolRegistry,
        rag_service: RagService,
        traces: TraceStore,
        sessions: SessionStore,
        generator: GenerationService | None = None,
    ) -> None:
        self.router = router
        self.registry = registry
        self.rag_service = rag_service
        self.traces = traces
        self.sessions = sessions
        self.generator = generator

    async def run(self, request: ChatRequest, sink: EventSink | None = None) -> ChatResponse:
        started = time.perf_counter()
        request_id = request.request_id or str(uuid4())
        session = self.sessions.get_or_create(request.session_id)
        session_id = session["session_id"]
        trace = self.traces.create(session_id=session_id, request_id=request_id)
        self.sessions.append_turn(session_id, "user", request.question, request_id=request_id)
        await self._emit(sink, "received", "Consulta recibida", request_id=request_id, trace_id=trace.trace_id)
        self.traces.append(trace.trace_id, TraceStage.RECEIVED, "Consulta recibida", question=request.question)

        route_started = time.perf_counter()
        decision = self.router.decide(request.question)
        strategy = request.strategy.value if request.strategy != RagStrategy.AUTO else decision.strategy
        route_ms = (time.perf_counter() - route_started) * 1000
        trace.intent = decision.intent
        trace.route = strategy
        self.traces.append(trace.trace_id, TraceStage.ROUTING, "Routing resuelto", intent=decision.intent, strategy=strategy, confidence=decision.confidence)
        await self._emit(sink, "routing", "Routing adaptativo", detail=f"{decision.intent} → {strategy}", confidence=decision.confidence)

        if decision.out_of_domain:
            answer = "La consulta está fuera del dominio de payment processing configurado para este laboratorio. Se requiere una pregunta relacionada con transacciones, autorización, adquirencia, conciliación, PCI o políticas de pagos."
            total_ms = (time.perf_counter() - started) * 1000
            trace.answer = answer
            provider = request.generation_provider.value
            model = request.model if provider == "openai" else "deterministic"
            trace.usage = {
                "input_tokens": self._token_count(request.question),
                "output_tokens": self._token_count(answer),
                "latency_ms": total_ms,
                "generation_provider": provider,
                "model": model,
                "prompt_version": request.prompt_version,
            }
            self.sessions.append_turn(session_id, "assistant", answer, trace_id=trace.trace_id)
            self.traces.append(trace.trace_id, TraceStage.COMPLETED, "Consulta fuera de dominio", total_ms=total_ms)
            await self._emit(sink, "completed", "Respuesta completada", answer=answer)
            return ChatResponse(
                session_id=session_id,
                request_id=request_id,
                trace_id=trace.trace_id,
                answer=answer,
                selected_strategy=strategy,
                intent=decision.intent,
                contexts=[],
                tools=[],
                timings_ms={"routing": route_ms, "retrieval": 0.0, "generation": 0.0, "total": total_ms},
                usage=trace.usage,
                generation_provider=provider,
                model=model,
                prompt_version=request.prompt_version,
            )

        tool_calls = []
        tx_match = _TX.search(request.question)
        transaction = None
        auth_code = None
        code_detail = None

        if tx_match:
            transaction_id = tx_match.group(0).upper()
            await self._emit(sink, "tool", "Consultando transacción", detail=transaction_id)
            call = await self.registry.invoke("get_transaction", {"transaction_id": transaction_id})
            tool_calls.append(call)
            trace.tool_calls.append(call)
            transaction = call.result if not call.error else None
            self.traces.append(trace.trace_id, TraceStage.TOOL, "get_transaction", arguments=call.arguments, ok=not bool(call.error), latency_ms=call.latency_ms)
            if transaction and transaction.get("found") and transaction.get("authorization_code"):
                auth_code = str(transaction["authorization_code"])

        if auth_code is None:
            code_match = _CODE.search(request.question)
            if code_match and any(term in request.question.lower() for term in ("código", "codigo", "autoriz")):
                auth_code = code_match.group(1)

        if auth_code:
            await self._emit(sink, "tool", "Interpretando código de autorización", detail=auth_code)
            call = await self.registry.invoke("lookup_authorization_code", {"code": auth_code})
            tool_calls.append(call)
            trace.tool_calls.append(call)
            code_detail = call.result if not call.error else None
            self.traces.append(trace.trace_id, TraceStage.TOOL, "lookup_authorization_code", arguments=call.arguments, ok=not bool(call.error), latency_ms=call.latency_ms)

        retrieval_started = time.perf_counter()
        await self._emit(sink, "retrieval", "Recuperando conocimiento", detail=f"estrategia={strategy}")
        contexts = await self.rag_service.retrieve(request.question, strategy=strategy, top_k=request.top_k)
        retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
        trace.retrieval = {
            "strategy": strategy,
            "contexts": [ctx.model_dump(mode="json") for ctx in contexts],
            "latency_ms": retrieval_ms,
        }
        self.traces.append(trace.trace_id, TraceStage.RETRIEVAL, "Retrieval completado", strategy=strategy, count=len(contexts), latency_ms=retrieval_ms)

        draft = None
        if request.include_case_draft and transaction and transaction.get("found") and transaction.get("status") == "declined" and code_detail and code_detail.get("found"):
            if code_detail.get("category") in {"issuer_unavailable", "do_not_honor", "suspected_fraud"}:
                priority = "high" if code_detail.get("category") == "suspected_fraud" else "medium"
                reason = f"Rechazo {auth_code}: {code_detail.get('meaning')}. {code_detail.get('recommended_action')}"
                call = await self.registry.invoke("create_case_draft", {"transaction_id": transaction["transaction_id"], "reason": reason, "priority": priority})
                tool_calls.append(call)
                trace.tool_calls.append(call)
                draft = call.result if not call.error else None
                self.traces.append(trace.trace_id, TraceStage.TOOL, "create_case_draft", arguments=call.arguments, ok=not bool(call.error), latency_ms=call.latency_ms)
                await self._emit(sink, "tool", "Borrador de caso generado", detail=str(draft.get("case_id") if draft else "sin borrador"))

        generation_started = time.perf_counter()
        provider = request.generation_provider.value
        requested_model = request.model if provider == "openai" else "deterministic"
        await self._emit(
            sink,
            "generation",
            "Generando respuesta fundamentada",
            detail=f"motor={provider} · modelo={requested_model} · prompt={request.prompt_version}",
            provider=provider,
            model=requested_model,
            prompt_version=request.prompt_version,
        )
        if self.generator is not None:
            generated = await self.generator.generate(
                question=request.question,
                transaction=transaction,
                code_detail=code_detail,
                contexts=contexts,
                draft=draft,
                provider=provider,
                model=request.model,
                prompt_version=request.prompt_version,
            )
            answer = generated.text
            provider = generated.provider
            requested_model = generated.model
            input_tokens = generated.input_tokens
            output_tokens = generated.output_tokens
            raw_usage = generated.raw_usage
        else:
            if provider != "deterministic":
                raise RuntimeError("El proveedor OpenAI no está disponible en este controlador")
            answer = self._compose_answer(request.question, transaction, code_detail, contexts, draft)
            input_tokens = self._token_count(request.question) + sum(self._token_count(ctx.text) for ctx in contexts)
            output_tokens = self._token_count(answer)
            raw_usage = {}
        generation_ms = (time.perf_counter() - generation_started) * 1000
        total_ms = (time.perf_counter() - started) * 1000
        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": total_ms,
            "generation_provider": provider,
            "model": requested_model,
            "prompt_version": request.prompt_version,
            "provider_usage": raw_usage,
        }
        trace.answer = answer
        trace.usage = usage
        trace.turns = list(session["turns"])
        self.sessions.append_turn(session_id, "assistant", answer, trace_id=trace.trace_id)
        self.traces.append(trace.trace_id, TraceStage.GENERATION, "Respuesta sintetizada", latency_ms=generation_ms)
        self.traces.append(trace.trace_id, TraceStage.COMPLETED, "Ejecución completada", total_ms=total_ms)
        self.traces.put(trace)
        await self._emit(sink, "completed", "Respuesta completada", answer=answer, trace_id=trace.trace_id)

        return ChatResponse(
            session_id=session_id,
            request_id=request_id,
            trace_id=trace.trace_id,
            answer=answer,
            selected_strategy=strategy,
            intent=decision.intent,
            contexts=contexts,
            tools=tool_calls,
            timings_ms={"routing": route_ms, "retrieval": retrieval_ms, "generation": generation_ms, "total": total_ms},
            usage=usage,
            generation_provider=provider,
            model=requested_model,
            prompt_version=request.prompt_version,
        )

    @staticmethod
    def _compose_answer(question: str, transaction: dict | None, code_detail: dict | None, contexts: list, draft: dict | None) -> str:
        parts: list[str] = []
        if transaction and transaction.get("found"):
            parts.append(
                f"La transacción {transaction['transaction_id']} figura como {transaction['status']} por {transaction['amount']:.2f} {transaction['currency']}, procesada por {transaction['acquirer']} hacia {transaction['issuer']}."
            )
        elif _TX.search(question):
            parts.append("No se encontró la transacción solicitada en el dataset controlado.")

        if code_detail and code_detail.get("found"):
            parts.append(
                f"El código de autorización {code_detail['code']} corresponde a “{code_detail['meaning']}”. La acción operativa indicada es: {code_detail['recommended_action']}"
            )
        if contexts:
            sources = ", ".join(dict.fromkeys(ctx.source for ctx in contexts[:3]))
            summary = contexts[0].text.replace("#", "").replace("\n", " ").strip()
            if len(summary) > 420:
                summary = summary[:417].rstrip() + "..."
            parts.append(f"La evidencia recuperada respalda el análisis: {summary}")
            parts.append(f"Fuentes consultadas: {sources}.")
        if draft and draft.get("draft"):
            parts.append(f"Se generó el borrador no destructivo {draft['case_id']} con prioridad {draft['priority']}; no se envió a ningún sistema externo.")
        if not parts:
            parts.append("Se recuperó conocimiento de pagos, pero no existe evidencia suficiente para una conclusión más específica en el dataset controlado.")
        return " ".join(parts)

    @staticmethod
    async def _emit(sink: EventSink | None, event: str, label: str, detail: str = "", **payload: object) -> None:
        if sink is not None:
            await sink({"event": event, "label": label, "detail": detail, **payload})

    @staticmethod
    def _token_count(text: str) -> int:
        return max(1, len(text.split()))
