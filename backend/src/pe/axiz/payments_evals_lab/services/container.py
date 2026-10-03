from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from pe.axiz.payments_evals_lab.agent.controller import AgenticController
from pe.axiz.payments_evals_lab.config.settings import Settings, get_settings
from pe.axiz.payments_evals_lab.evals.suite_runner import EvaluationSuiteRunner
from pe.axiz.payments_evals_lab.observability.tracing import trace_store
from pe.axiz.payments_evals_lab.rag.router import AdaptiveRouter
from pe.axiz.payments_evals_lab.rag.service import RagService
from pe.axiz.payments_evals_lab.repositories.payment_repository import PaymentRepository
from pe.axiz.payments_evals_lab.services.generation import GenerationService
from pe.axiz.payments_evals_lab.services.session_store import session_store
from pe.axiz.payments_evals_lab.tools.payment_tools import build_tool_registry
from pe.axiz.payments_evals_lab.tools.registry import ToolRegistry


@dataclass(frozen=True)
class AppContainer:
    settings: Settings
    repository: PaymentRepository
    rag: RagService
    router: AdaptiveRouter
    tools: ToolRegistry
    controller: AgenticController
    eval_runner: EvaluationSuiteRunner


@lru_cache
def get_container() -> AppContainer:
    settings = get_settings()
    repository = PaymentRepository(settings.datasets_dir)
    rag = RagService(settings)
    router = AdaptiveRouter()
    tools = build_tool_registry(repository, rag)
    generation = GenerationService(settings)
    controller = AgenticController(router, tools, rag, trace_store, session_store, generation)
    runner = EvaluationSuiteRunner(settings, controller, rag, router, tools)
    return AppContainer(settings, repository, rag, router, tools, controller, runner)
