from pathlib import Path

import pytest

from pe.axiz.payments_evals_lab.agent.controller import AgenticController
from pe.axiz.payments_evals_lab.config.settings import Settings
from pe.axiz.payments_evals_lab.domain.models import ChatRequest
from pe.axiz.payments_evals_lab.observability.tracing import TraceStore
from pe.axiz.payments_evals_lab.rag.router import AdaptiveRouter
from pe.axiz.payments_evals_lab.rag.service import RagService
from pe.axiz.payments_evals_lab.repositories.payment_repository import PaymentRepository
from pe.axiz.payments_evals_lab.services.session_store import SessionStore
from pe.axiz.payments_evals_lab.tools.payment_tools import build_tool_registry


@pytest.mark.asyncio
async def test_transaction_diagnosis_is_observable_and_non_destructive() -> None:
    settings = Settings(datasets_dir=Path("datasets"))
    repo = PaymentRepository(settings.datasets_dir)
    rag = RagService(settings)
    tools = build_tool_registry(repo, rag)
    traces = TraceStore()
    controller = AgenticController(AdaptiveRouter(), tools, rag, traces, SessionStore())

    response = await controller.run(ChatRequest(question="Revisa TX-1007 y explica el rechazo", strategy="hybrid"))
    assert "TX-1007" in response.answer
    assert "91" in response.answer
    assert any(call.tool == "get_transaction" for call in response.tools)
    assert any(call.tool == "lookup_authorization_code" for call in response.tools)
    draft_calls = [call for call in response.tools if call.tool == "create_case_draft"]
    assert draft_calls and draft_calls[0].result["status"] == "not_submitted"

    trace = traces.get(response.trace_id)
    assert trace is not None
    serialized = trace.model_dump(mode="json")
    assert "chain_of_thought" not in serialized
    assert "reasoning" not in serialized
