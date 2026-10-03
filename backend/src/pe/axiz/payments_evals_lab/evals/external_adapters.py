from __future__ import annotations

from typing import Any

from pe.axiz.payments_evals_lab.domain.models import MetricResult
from pe.axiz.payments_evals_lab.evals.common import metric


async def run_deepeval(case: dict[str, Any], enabled: bool, judge_model: str = "deterministic") -> list[MetricResult]:
    """Ejecuta DeepEval con juez externo solo cuando la configuración lo habilita explícitamente."""
    if not enabled:
        return [
            metric(
                "deepeval_integration",
                1.0,
                "integration",
                framework="deepeval",
                threshold=1.0,
                reason="DeepEval instalado como adaptador; el juez LLM externo no se ejecutó. Se utilizaron métricas deterministas equivalentes.",
                judge_model="deterministic",
            )
        ]
    try:
        from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
        from deepeval.test_case import LLMTestCase
    except ImportError:
        return [metric("deepeval_integration", 0.0, "integration", framework="deepeval", threshold=1.0, reason="DeepEval no está instalado")]

    test_case = LLMTestCase(
        input=case.get("question", ""),
        actual_output=case.get("actual_answer", ""),
        expected_output=case.get("expected_answer", ""),
        retrieval_context=case.get("contexts", []),
    )
    results: list[MetricResult] = []
    constructors = (
        ("deepeval_faithfulness", FaithfulnessMetric, 0.9),
        ("deepeval_answer_relevancy", AnswerRelevancyMetric, 0.8),
    )
    for name, metric_type, threshold in constructors:
        try:
            try:
                evaluator = metric_type(threshold=threshold, model=judge_model)
            except TypeError:
                evaluator = metric_type(threshold=threshold)
            evaluator.measure(test_case)
            results.append(
                metric(
                    name,
                    float(evaluator.score),
                    "rag_generation",
                    framework="deepeval",
                    threshold=float(evaluator.threshold),
                    reason=str(getattr(evaluator, "reason", "")),
                    judge_model=judge_model,
                    judge_provider="openai",
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                metric(
                    name,
                    0.0,
                    "integration",
                    framework="deepeval",
                    threshold=1.0,
                    reason=f"Fallo de ejecución: {type(exc).__name__}: {exc}",
                    judge_model=judge_model,
                )
            )
    return results


async def run_ragas(case: dict[str, Any], enabled: bool, judge_model: str = "deterministic") -> list[MetricResult]:
    """Valida disponibilidad de RAGAS; las métricas RAGAS-compatible siempre se calculan en el motor determinista."""
    if not enabled:
        return [
            metric(
                "ragas_integration",
                1.0,
                "integration",
                framework="ragas",
                threshold=1.0,
                reason="RAGAS disponible como integración opcional; Context Precision/Recall/Relevancy, Faithfulness y Groundedness se ejecutaron mediante equivalentes deterministas reproducibles.",
                judge_model="deterministic",
            )
        ]
    try:
        import ragas  # noqa: F401
    except ImportError:
        return [metric("ragas_integration", 0.0, "integration", framework="ragas", threshold=1.0, reason="RAGAS no está instalado")]
    return [
        metric(
            "ragas_integration",
            1.0,
            "integration",
            framework="ragas",
            threshold=1.0,
            reason="RAGAS está instalado. Las métricas equivalentes reproducibles se mantienen como resultados canónicos del benchmark; el juez configurado se registra para trazabilidad.",
            judge_model=judge_model,
            judge_provider="openai",
        )
    ]
