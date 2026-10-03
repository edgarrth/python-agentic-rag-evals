from __future__ import annotations

from statistics import mean, pstdev
from typing import Any

from pe.axiz.payments_evals_lab.evals.common import clamp, metric, percentile


def latency_score(value_ms: float, budget_ms: float) -> float:
    if value_ms <= budget_ms:
        return 1.0
    return clamp(budget_ms / value_ms)


def evaluate_performance(case: dict[str, Any]) -> list:
    retrieval = [float(v) for v in case.get("retrieval_latency_ms", [])]
    generation = [float(v) for v in case.get("generation_latency_ms", [])]
    total = [float(v) for v in case.get("total_latency_ms", [])]
    ttfc = [float(v) for v in case.get("ttfc_ms", [])]
    input_tokens = int(case.get("input_tokens", 0))
    output_tokens = int(case.get("output_tokens", 0))
    input_rate = float(case.get("input_cost_per_million", 1.25))
    output_rate = float(case.get("output_cost_per_million", 10.0))
    cost = input_tokens / 1_000_000 * input_rate + output_tokens / 1_000_000 * output_rate
    results = []
    for name, values, budget in (
        ("retrieval_latency", retrieval, case.get("retrieval_budget_ms", 500.0)),
        ("generation_latency", generation, case.get("generation_budget_ms", 2500.0)),
        ("total_latency", total, case.get("total_budget_ms", 3000.0)),
    ):
        if values:
            results.append(metric(name, latency_score(percentile(values, 0.95), float(budget)), "performance", threshold=1.0, p50_ms=percentile(values, 0.5), p95_ms=percentile(values, 0.95), p99_ms=percentile(values, 0.99), mean_ms=mean(values), budget_ms=budget))
    if ttfc:
        budget = float(case.get("ttfc_budget_ms", 900.0))
        results.append(metric("text_ttfc", latency_score(percentile(ttfc, 0.95), budget), "performance", threshold=1.0, p95_ms=percentile(ttfc, 0.95), budget_ms=budget))
    results.append(metric("token_budget", 1.0 if input_tokens + output_tokens <= int(case.get("token_budget", 8000)) else clamp(case.get("token_budget", 8000) / max(1, input_tokens + output_tokens)), "performance", threshold=1.0, input_tokens=input_tokens, output_tokens=output_tokens))
    results.append(metric("estimated_cost_budget", 1.0 if cost <= float(case.get("cost_budget", 0.05)) else clamp(float(case.get("cost_budget", 0.05)) / max(cost, 1e-9)), "performance", threshold=1.0, estimated_cost=cost))
    if total and len(total) > 1:
        coefficient = pstdev(total) / max(mean(total), 1e-9)
        results.append(metric("load_latency_stability", clamp(1.0 - coefficient), "performance", threshold=0.8, coefficient_of_variation=coefficient))
    return results
