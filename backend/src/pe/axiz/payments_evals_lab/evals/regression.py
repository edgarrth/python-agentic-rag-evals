from __future__ import annotations

import math
from statistics import mean
from typing import Any

from pe.axiz.payments_evals_lab.evals.common import clamp, metric, safe_div


def population_stability_index(expected: list[float], actual: list[float], bins: int = 10) -> float:
    if not expected or not actual:
        return 0.0
    low = min(expected + actual)
    high = max(expected + actual)
    if math.isclose(low, high):
        return 0.0
    width = (high - low) / bins
    psi = 0.0
    for index in range(bins):
        left = low + index * width
        right = high + (index + 1) * width
        e = sum(1 for value in expected if left <= value < right or (index == bins - 1 and value == right)) / len(expected)
        a = sum(1 for value in actual if left <= value < right or (index == bins - 1 and value == right)) / len(actual)
        e = max(e, 1e-6)
        a = max(a, 1e-6)
        psi += (a - e) * math.log(a / e)
    return psi


def evaluate_regression(case: dict[str, Any]) -> list:
    baseline = case.get("baseline_metrics", {})
    candidate = case.get("candidate_metrics", {})
    allowed_delta = float(case.get("allowed_regression_delta", 0.03))
    critical = set(case.get("critical_metrics", baseline.keys()))
    deltas = {name: candidate.get(name, 0.0) - value for name, value in baseline.items() if name in candidate}
    passed = [name for name, delta in deltas.items() if name not in critical or delta >= -allowed_delta]
    regression_score = safe_div(len(passed), len(deltas)) if deltas else 1.0

    expected_dist = [float(v) for v in case.get("baseline_distribution", [])]
    current_dist = [float(v) for v in case.get("current_distribution", [])]
    psi = population_stability_index(expected_dist, current_dist) if expected_dist and current_dist else 0.0
    data_drift_score = 1.0 if psi < 0.1 else (0.5 if psi < 0.25 else 0.0)

    baseline_accuracy = float(case.get("baseline_accuracy", 1.0))
    current_accuracy = float(case.get("current_accuracy", baseline_accuracy))
    baseline_f1 = float(case.get("baseline_f1", 1.0))
    current_f1 = float(case.get("current_f1", baseline_f1))
    degradation = mean([max(0.0, baseline_accuracy - current_accuracy), max(0.0, baseline_f1 - current_f1)])
    concept_drift_score = clamp(1.0 - degradation / max(allowed_delta, 1e-9))

    golden = case.get("golden_results", [])
    golden_pass = safe_div(sum(1 for item in golden if item.get("passed")), len(golden)) if golden else 1.0
    temporal = case.get("temporal_scores", [])
    temporal_score = 1.0
    if len(temporal) >= 2:
        drop = temporal[0] - temporal[-1]
        temporal_score = clamp(1.0 - max(0.0, drop) / max(allowed_delta, 1e-9))

    return [
        metric("golden_regression", golden_pass, "regression", threshold=1.0),
        metric("baseline_candidate_regression", regression_score, "regression", threshold=1.0, deltas=deltas, allowed_delta=allowed_delta),
        metric("data_drift", data_drift_score, "drift", threshold=0.5, psi=psi),
        metric("concept_drift", concept_drift_score, "drift", threshold=0.5, accuracy_delta=current_accuracy - baseline_accuracy, f1_delta=current_f1 - baseline_f1),
        metric("temporal_degradation", temporal_score, "drift", threshold=0.5, scores=temporal),
    ]
