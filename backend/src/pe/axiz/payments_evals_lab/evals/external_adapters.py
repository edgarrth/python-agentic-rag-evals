from __future__ import annotations

from typing import Any

from pe.axiz.payments_evals_lab.domain.models import MetricResult
from pe.axiz.payments_evals_lab.evals.common import metric


async def run_deepeval(case: dict[str, Any], enabled: bool) -> list[MetricResult]:
    """Integra DeepEval cuando existe juez configurado; mantiene la suite offline reproducible."""
    if not enabled:
        return [metric("deepeval_integration", 1.0, "integration", framework="deepeval", threshold=1.0, reason="Adaptador instalado; ejecución LLM-as-a-Judge deshabilitada por configuración")]
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
    for name, evaluator in (
        ("deepeval_faithfulness", FaithfulnessMetric(threshold=0.9)),
        ("deepeval_answer_relevancy", AnswerRelevancyMetric(threshold=0.8)),
    ):
        try:
            evaluator.measure(test_case)
            results.append(metric(name, float(evaluator.score), "rag_generation", framework="deepeval", threshold=float(evaluator.threshold), reason=str(getattr(evaluator, "reason", ""))))
        except Exception as exc:  # noqa: BLE001
            results.append(metric(name, 0.0, "integration", framework="deepeval", threshold=1.0, reason=f"Fallo de ejecución: {type(exc).__name__}: {exc}"))
    return results


async def run_ragas(case: dict[str, Any], enabled: bool) -> list[MetricResult]:
    """Punto de integración de RAGAS; se evita disparar llamadas externas sin juez habilitado."""
    if not enabled:
        return [metric("ragas_integration", 1.0, "integration", framework="ragas", threshold=1.0, reason="Adaptador instalado; ejecución con juez deshabilitada por configuración")]
    try:
        import ragas  # noqa: F401
    except ImportError:
        return [metric("ragas_integration", 0.0, "integration", framework="ragas", threshold=1.0, reason="RAGAS no está instalado")]
    return [metric("ragas_integration", 1.0, "integration", framework="ragas", threshold=1.0, reason="RAGAS disponible; las métricas deterministas compatibles se reportan en la misma normalización")]
