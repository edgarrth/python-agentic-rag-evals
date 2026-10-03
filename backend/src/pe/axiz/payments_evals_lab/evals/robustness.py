from __future__ import annotations

from statistics import mean
from typing import Any

from pe.axiz.payments_evals_lab.evals.classic import self_consistency
from pe.axiz.payments_evals_lab.evals.common import metric, safe_div


def evaluate_robustness(case: dict[str, Any]) -> list:
    outputs = case.get("repeated_outputs", [])
    retries = case.get("retries", [])
    fallback = case.get("fallback", {})
    failures = case.get("failures", [])
    flow_steps = case.get("flow_steps", [])

    fallback_score = 1.0 if fallback.get("expected_action") == fallback.get("actual_action") else 0.0
    retry_successes = sum(1 for item in retries if item.get("recovered"))
    retry_score = safe_div(retry_successes, len(retries)) if retries else 1.0
    recoveries = sum(1 for item in failures if item.get("recovered"))
    recovery_score = safe_div(recoveries, len(failures)) if failures else 1.0
    graceful = mean([float(item.get("graceful", False)) for item in failures]) if failures else 1.0
    flow_expected = [item.get("expected") for item in flow_steps]
    flow_actual = [item.get("actual") for item in flow_steps]
    flow_score = safe_div(sum(1 for e, a in zip(flow_expected, flow_actual, strict=True) if e == a), len(flow_expected)) if flow_expected else 1.0
    consistency = self_consistency(outputs) if outputs else 1.0
    return [
        metric("self_consistency", consistency, "robustness", threshold=0.75),
        metric("fallback_correctness", fallback_score, "robustness", threshold=1.0),
        metric("retry_correctness", retry_score, "robustness", threshold=0.9),
        metric("failure_recovery", recovery_score, "robustness", threshold=0.9),
        metric("graceful_degradation", graceful, "robustness", threshold=0.9),
        metric("conversational_flow_consistency", flow_score, "robustness", threshold=0.9),
    ]
