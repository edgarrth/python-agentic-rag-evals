from pathlib import Path

import pytest

from pe.axiz.payments_evals_lab.agent.controller import AgenticController
from pe.axiz.payments_evals_lab.config.settings import Settings
from pe.axiz.payments_evals_lab.domain.models import GenerationProvider, RagStrategy
from pe.axiz.payments_evals_lab.evals.suite_runner import EvaluationSuiteRunner
from pe.axiz.payments_evals_lab.observability.tracing import TraceStore
from pe.axiz.payments_evals_lab.rag.router import AdaptiveRouter
from pe.axiz.payments_evals_lab.rag.service import RagService
from pe.axiz.payments_evals_lab.repositories.payment_repository import PaymentRepository
from pe.axiz.payments_evals_lab.services.generation import GenerationService
from pe.axiz.payments_evals_lab.services.session_store import SessionStore
from pe.axiz.payments_evals_lab.tools.payment_tools import build_tool_registry


@pytest.mark.asyncio
async def test_rag_benchmark_executes_all_five_strategies_with_same_configuration() -> None:
    settings = Settings(datasets_dir=Path("datasets"), eval_judge_enabled=False)
    repo = PaymentRepository(settings.datasets_dir)
    rag = RagService(settings)
    router = AdaptiveRouter()
    tools = build_tool_registry(repo, rag)
    controller = AgenticController(router, tools, rag, TraceStore(), SessionStore(), GenerationService(settings))
    runner = EvaluationSuiteRunner(settings, controller, rag, router, tools)

    strategies = [RagStrategy.NATIVE, RagStrategy.HYBRID, RagStrategy.GRAPHRAG, RagStrategy.RAGLIGHT, RagStrategy.LIGHTRAG]
    observed = {}
    for strategy in strategies:
        metrics, _, _, _ = await runner.run(
            "rag",
            strategy,
            external_judges=False,
            generation_provider=GenerationProvider.DETERMINISTIC,
            model="deterministic",
            prompt_version="v1",
            top_k=5,
        )
        assert metrics
        assert {item.strategy for item in metrics if item.strategy} == {strategy.value}
        assert all(item.prompt_version == "v1" for item in metrics)
        assert all(item.details.get("sut_generation_provider") == "deterministic" for item in metrics)
        observed[strategy.value] = {item.metric for item in metrics}

    assert set(observed) == {item.value for item in strategies}
    common = set.intersection(*observed.values())
    assert {"mrr", "context_precision", "context_recall", "faithfulness", "groundedness", "correctness"} <= common
