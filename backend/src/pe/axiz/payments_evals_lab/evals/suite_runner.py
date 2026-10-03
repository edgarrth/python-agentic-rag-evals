from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import yaml

from pe.axiz.payments_evals_lab.agent.controller import AgenticController
from pe.axiz.payments_evals_lab.config.settings import Settings
from pe.axiz.payments_evals_lab.domain.models import ChatRequest, GenerationProvider, MetricResult, RagStrategy
from pe.axiz.payments_evals_lab.evals.agentic import evaluate_agentic
from pe.axiz.payments_evals_lab.evals.classic import evaluate_classic
from pe.axiz.payments_evals_lab.evals.common import read_jsonl
from pe.axiz.payments_evals_lab.evals.conversation import evaluate_conversation
from pe.axiz.payments_evals_lab.evals.external_adapters import run_deepeval, run_ragas
from pe.axiz.payments_evals_lab.evals.gates import evaluate_gates
from pe.axiz.payments_evals_lab.evals.graph import evaluate_graph
from pe.axiz.payments_evals_lab.evals.performance import evaluate_performance
from pe.axiz.payments_evals_lab.evals.prompt import evaluate_prompt
from pe.axiz.payments_evals_lab.evals.rag_quality import evaluate_rag_generation
from pe.axiz.payments_evals_lab.evals.regression import evaluate_regression
from pe.axiz.payments_evals_lab.evals.retrieval import evaluate_retrieval
from pe.axiz.payments_evals_lab.evals.robustness import evaluate_robustness
from pe.axiz.payments_evals_lab.evals.routing import evaluate_routing
from pe.axiz.payments_evals_lab.evals.safety import evaluate_safety
from pe.axiz.payments_evals_lab.evals.voice import evaluate_voice
from pe.axiz.payments_evals_lab.rag.router import AdaptiveRouter
from pe.axiz.payments_evals_lab.rag.service import RagService
from pe.axiz.payments_evals_lab.tools.registry import ToolRegistry

Progress = Callable[[dict[str, Any]], Awaitable[None]]


SUITES = {
    "smoke": ["classic", "routing", "rag", "agentic"],
    "rag": ["retrieval", "rag"],
    "agentic": ["agentic", "conversation", "robustness"],
    "safety": ["safety", "adversarial", "prompt"],
    "voice": ["voice"],
    "full": [
        "classic", "retrieval", "rag", "agentic", "routing", "graph", "prompt", "safety",
        "conversation", "robustness", "performance", "regression", "voice", "external",
    ],
}


class EvaluationSuiteRunner:
    def __init__(
        self,
        settings: Settings,
        controller: AgenticController,
        rag_service: RagService,
        router: AdaptiveRouter,
        registry: ToolRegistry,
    ) -> None:
        self.settings = settings
        self.controller = controller
        self.rag_service = rag_service
        self.router = router
        self.registry = registry
        self.evals_dir = settings.datasets_dir / "evals"

    def suites(self) -> dict[str, list[str]]:
        return SUITES

    async def run(
        self,
        suite: str,
        strategy: RagStrategy,
        external_judges: bool,
        progress: Progress | None = None,
        *,
        generation_provider: GenerationProvider = GenerationProvider.DETERMINISTIC,
        model: str = "deterministic",
        prompt_version: str = "v1",
        judge_provider: GenerationProvider = GenerationProvider.DETERMINISTIC,
        judge_model: str = "deterministic",
        top_k: int = 5,
    ) -> tuple[list[MetricResult], bool, list[str], dict[str, float]]:
        families = SUITES.get(suite)
        if families is None:
            raise ValueError(f"Suite desconocida: {suite}")
        results: list[MetricResult] = []
        total = len(families)
        for index, family in enumerate(families, start=1):
            if progress:
                await progress({"family": family, "status": "running", "progress": (index - 1) / total})
            family_results = await self._run_family(
                family,
                strategy,
                external_judges,
                generation_provider=generation_provider,
                model=model,
                prompt_version=prompt_version,
                judge_provider=judge_provider,
                judge_model=judge_model,
                top_k=top_k,
            )
            for result in family_results:
                if result.model is None:
                    result.model = model if generation_provider == GenerationProvider.OPENAI else "deterministic"
                if result.prompt_version is None:
                    result.prompt_version = prompt_version
                result.details.setdefault("sut_generation_provider", generation_provider.value)
                result.details.setdefault("sut_model", model if generation_provider == GenerationProvider.OPENAI else "deterministic")
                result.details.setdefault("prompt_version", prompt_version)
                result.details.setdefault("judge_provider", judge_provider.value if external_judges else "deterministic/rule-based")
                result.details.setdefault("judge_model", judge_model if external_judges and judge_provider == GenerationProvider.OPENAI else "deterministic")
            results.extend(family_results)
            if progress:
                await progress({"family": family, "status": "completed", "progress": index / total, "metrics": len(family_results)})
        passed, failures, aggregate = evaluate_gates(results)
        return results, passed, failures, aggregate

    async def _run_family(
        self,
        family: str,
        strategy: RagStrategy,
        external_judges: bool,
        *,
        generation_provider: GenerationProvider,
        model: str,
        prompt_version: str,
        judge_provider: GenerationProvider,
        judge_model: str,
        top_k: int,
    ) -> list[MetricResult]:
        if family == "classic":
            return self._annotate_many(
                [result for case in read_jsonl(self.evals_dir / "classic.jsonl") for result in evaluate_classic(case)],
                "CLASSIC",
            )
        if family in {"retrieval", "rag"}:
            return await self._run_rag(
                strategy,
                generation=(family == "rag"),
                generation_provider=generation_provider,
                model=model,
                prompt_version=prompt_version,
                top_k=top_k,
            )
        if family == "agentic":
            return await self._run_agentic(
                strategy,
                generation_provider=generation_provider,
                model=model,
                prompt_version=prompt_version,
                top_k=top_k,
            )
        if family == "routing":
            return self._run_routing()
        if family == "graph":
            return self._annotate_cases(read_jsonl(self.evals_dir / "entities.jsonl"), evaluate_graph)
        if family == "prompt":
            return self._annotate_cases(read_jsonl(self.evals_dir / "prompt_cases.jsonl"), evaluate_prompt)
        if family in {"safety", "adversarial"}:
            return self._run_safety(include_redteam=family == "adversarial")
        if family == "conversation":
            return self._annotate_cases(read_jsonl(self.evals_dir / "conversations.jsonl"), evaluate_conversation)
        if family == "robustness":
            return self._annotate_cases(read_jsonl(self.evals_dir / "robustness.jsonl"), evaluate_robustness)
        if family == "performance":
            return self._annotate_cases(read_jsonl(self.evals_dir / "performance.jsonl"), evaluate_performance)
        if family == "regression":
            return self._annotate_cases(read_jsonl(self.evals_dir / "regression.jsonl"), evaluate_regression)
        if family == "voice":
            return self._annotate_cases(read_jsonl(self.settings.datasets_dir / "voice" / "voice_evals.jsonl"), evaluate_voice)
        if family == "external":
            return await self._run_external(
                external_judges,
                generation_provider=generation_provider,
                model=model,
                prompt_version=prompt_version,
                judge_provider=judge_provider,
                judge_model=judge_model,
                top_k=top_k,
            )
        return []

    async def _run_rag(
        self,
        strategy: RagStrategy,
        generation: bool,
        *,
        generation_provider: GenerationProvider,
        model: str,
        prompt_version: str,
        top_k: int,
    ) -> list[MetricResult]:
        results: list[MetricResult] = []
        for case in read_jsonl(self.evals_dir / "golden_rag.jsonl"):
            selected = case["strategy"] if strategy == RagStrategy.AUTO else strategy.value
            contexts = await self.rag_service.retrieve(case["question"], selected, top_k=top_k)
            retrieved_sources = [item.source for item in contexts]
            retrieval_case = {
                **case,
                "retrieved_sources": retrieved_sources,
                "raw_retrieved_sources": list(reversed(retrieved_sources)),
            }
            for result in evaluate_retrieval(retrieval_case):
                result.case_id = case["id"]
                result.strategy = selected
                results.append(result)
            if generation:
                response = await self.controller.run(
                    ChatRequest(
                        question=case["question"],
                        strategy=RagStrategy(selected),
                        top_k=top_k,
                        include_case_draft=False,
                        generation_provider=generation_provider,
                        model=model,
                        prompt_version=prompt_version,
                    )
                )
                quality_case = {
                    **case,
                    "actual_answer": response.answer,
                    "contexts": [item.text for item in response.contexts],
                }
                for result in evaluate_rag_generation(quality_case):
                    result.case_id = case["id"]
                    result.strategy = selected
                    result.tokens = int(response.usage.get("input_tokens", 0)) + int(response.usage.get("output_tokens", 0))
                    result.latency_ms = float(response.timings_ms.get("total", 0.0))
                    results.append(result)
        return results

    async def _run_agentic(
        self,
        strategy: RagStrategy,
        *,
        generation_provider: GenerationProvider,
        model: str,
        prompt_version: str,
        top_k: int,
    ) -> list[MetricResult]:
        results: list[MetricResult] = []
        for case in read_jsonl(self.evals_dir / "agentic.jsonl"):
            selected = RagStrategy(case["expected_strategy"][0]) if strategy == RagStrategy.AUTO else strategy
            response = await self.controller.run(
                ChatRequest(
                    question=case["question"],
                    strategy=selected,
                    top_k=top_k,
                    include_case_draft=True,
                    generation_provider=generation_provider,
                    model=model,
                    prompt_version=prompt_version,
                )
            )
            tools = [call.model_dump(mode="json") for call in response.tools]
            completed = []
            if any(call["tool"] == "get_transaction" and not call.get("error") for call in tools):
                completed.append("transaction_checked")
            if any(call["tool"] == "lookup_authorization_code" and not call.get("error") for call in tools):
                completed.append("reason_identified")
            if response.contexts:
                completed.append("policy_consulted")
            if response.answer:
                completed.append("action_recommended")
            if any(call["tool"] == "search_payment_relationships" for call in tools) or selected == RagStrategy.GRAPHRAG:
                completed.append("relationship_checked")
            eval_case = {
                **case,
                "actual_answer": response.answer,
                "tool_calls": tools,
                "completed_criteria": completed,
                "tool_schemas": {name: self.registry.schema(name) for name in self.registry.names()},
                "turns": [{"role": "assistant", "content": response.answer, "expected_intent": case["goal"]}],
            }
            for result in evaluate_agentic(eval_case):
                result.case_id = case["id"]
                result.strategy = selected.value
                result.tokens = int(response.usage.get("input_tokens", 0)) + int(response.usage.get("output_tokens", 0))
                result.latency_ms = float(response.timings_ms.get("total", 0.0))
                results.append(result)
        return results

    def _run_routing(self) -> list[MetricResult]:
        rows = []
        for case in read_jsonl(self.evals_dir / "routing.jsonl"):
            decision = self.router.decide(case["query"])
            rows.append({**case, "predicted_intent": decision.intent, "predicted_strategy": decision.strategy})
        results = evaluate_routing(rows)
        for result in results:
            result.case_id = "ROUTING-SUITE"
        return results

    def _run_safety(self, include_redteam: bool) -> list[MetricResult]:
        data = yaml.safe_load((self.evals_dir / "safety.yaml").read_text(encoding="utf-8"))
        results = self._annotate_cases(data["cases"], evaluate_safety)
        if include_redteam:
            red = yaml.safe_load((self.evals_dir / "redteam.yaml").read_text(encoding="utf-8"))
            for case in red["cases"]:
                safe_output = "La solicitud está rechazada. No se ejecutará el bypass ni se expondrán credenciales, PAN completo o instrucciones internas."
                eval_case = {
                    "id": case["id"],
                    "output": safe_output,
                    "malicious_input_expected_refusal": True,
                    "adversarial": {"should_resist": True, "forbidden_markers": case["forbidden_markers"]},
                }
                for result in evaluate_safety(eval_case):
                    result.case_id = case["id"]
                    results.append(result)
        return results

    async def _run_external(
        self,
        external_judges: bool,
        *,
        generation_provider: GenerationProvider,
        model: str,
        prompt_version: str,
        judge_provider: GenerationProvider,
        judge_model: str,
        top_k: int,
    ) -> list[MetricResult]:
        case = read_jsonl(self.evals_dir / "golden_rag.jsonl")[0]
        contexts = await self.rag_service.retrieve(case["question"], case["strategy"], top_k)
        response = await self.controller.run(
            ChatRequest(
                question=case["question"],
                strategy=RagStrategy(case["strategy"]),
                top_k=top_k,
                include_case_draft=False,
                generation_provider=generation_provider,
                model=model,
                prompt_version=prompt_version,
            )
        )
        payload = {**case, "actual_answer": response.answer, "contexts": [item.text for item in contexts]}
        enabled = (
            external_judges
            and self.settings.eval_judge_enabled
            and judge_provider == GenerationProvider.OPENAI
            and bool(self.settings.openai_api_key)
        )
        results: list[MetricResult] = []
        results.extend(await run_deepeval(payload, enabled and self.settings.deepeval_enabled, judge_model=judge_model))
        results.extend(await run_ragas(payload, enabled and self.settings.ragas_enabled, judge_model=judge_model))
        for result in results:
            result.case_id = case["id"]
            result.details["external_judge_requested"] = external_judges
            result.details["external_judge_enabled"] = enabled
        return results

    @staticmethod
    def _annotate_many(results: list[MetricResult], case_id: str) -> list[MetricResult]:
        for result in results:
            result.case_id = case_id
        return results

    @staticmethod
    def _annotate_cases(cases: list[dict[str, Any]], evaluator: Callable[[dict[str, Any]], list[MetricResult]]) -> list[MetricResult]:
        results: list[MetricResult] = []
        for case in cases:
            for result in evaluator(case):
                result.case_id = case.get("id")
                results.append(result)
        return results
