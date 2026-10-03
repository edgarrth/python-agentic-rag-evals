from __future__ import annotations

import math
from collections import Counter
from statistics import mean, pstdev
from typing import Any

from pe.axiz.payments_evals_lab.evals.common import classification_summary, clamp, metric, safe_div, token_jaccard


def _ngrams(tokens: list[str], n: int) -> Counter[tuple[str, ...]]:
    return Counter(tuple(tokens[i : i + n]) for i in range(max(0, len(tokens) - n + 1)))


def bleu_score(reference: str, candidate: str, max_n: int = 4) -> float:
    ref = reference.lower().split()
    cand = candidate.lower().split()
    if not cand:
        return 0.0
    precisions = []
    for n in range(1, max_n + 1):
        c = _ngrams(cand, n)
        r = _ngrams(ref, n)
        total = sum(c.values())
        clipped = sum(min(count, r[gram]) for gram, count in c.items())
        precisions.append((clipped + 1.0) / (total + 1.0))
    geo = math.exp(sum(math.log(value) for value in precisions) / max_n)
    brevity = 1.0 if len(cand) > len(ref) else math.exp(1 - safe_div(len(ref), len(cand)))
    return clamp(brevity * geo)


def _lcs(a: list[str], b: list[str]) -> int:
    prev = [0] * (len(b) + 1)
    for token_a in a:
        cur = [0]
        for j, token_b in enumerate(b, start=1):
            cur.append(prev[j - 1] + 1 if token_a == token_b else max(prev[j], cur[-1]))
        prev = cur
    return prev[-1]


def rouge_l(reference: str, candidate: str) -> float:
    ref, cand = reference.lower().split(), candidate.lower().split()
    if not ref or not cand:
        return 0.0
    lcs = _lcs(ref, cand)
    precision = safe_div(lcs, len(cand))
    recall = safe_div(lcs, len(ref))
    return safe_div(2 * precision * recall, precision + recall)


def log_loss_binary(y_true: list[int], probabilities: list[float]) -> float:
    eps = 1e-12
    values = []
    for actual, probability in zip(y_true, probabilities, strict=True):
        p = min(1 - eps, max(eps, probability))
        values.append(-(actual * math.log(p) + (1 - actual) * math.log(1 - p)))
    return mean(values) if values else 0.0


def brier_score(y_true: list[int], probabilities: list[float]) -> float:
    return mean((probability - actual) ** 2 for actual, probability in zip(y_true, probabilities, strict=True)) if y_true else 0.0


def expected_calibration_error(y_true: list[int], probabilities: list[float], bins: int = 5) -> float:
    if not y_true:
        return 0.0
    error = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [(actual, prob) for actual, prob in zip(y_true, probabilities, strict=True) if low <= prob < high or (index == bins - 1 and prob == 1.0)]
        if not members:
            continue
        accuracy = mean(actual for actual, _ in members)
        confidence = mean(prob for _, prob in members)
        error += len(members) / len(y_true) * abs(accuracy - confidence)
    return error


def self_consistency(outputs: list[str]) -> float:
    if len(outputs) < 2:
        return 1.0
    pairs = [token_jaccard(outputs[i], outputs[j]) for i in range(len(outputs)) for j in range(i + 1, len(outputs))]
    return mean(pairs) if pairs else 1.0


def evaluate_classic(case: dict[str, Any]) -> list:
    results = []
    if case.get("classification"):
        summary = classification_summary(case["classification"]["y_true"], case["classification"]["y_pred"])
        for name in ("accuracy", "precision_macro", "recall_macro", "f1_macro"):
            results.append(metric(name, summary[name], "classic", threshold=case.get("threshold", 0.8), confusion_matrix=summary["confusion_matrix"]))
    if case.get("probabilities"):
        y_true = case["probabilities"]["y_true"]
        y_prob = case["probabilities"]["y_prob"]
        loss = log_loss_binary(y_true, y_prob)
        brier = brier_score(y_true, y_prob)
        ece = expected_calibration_error(y_true, y_prob)
        results.append(metric("log_loss", max(0.0, 1.0 - min(1.0, loss)), "classic", threshold=0.6, raw_loss=loss))
        results.append(metric("brier_calibration", max(0.0, 1.0 - brier), "uncertainty", threshold=0.8, raw_brier=brier))
        results.append(metric("expected_calibration_error", max(0.0, 1.0 - ece), "uncertainty", threshold=0.8, raw_ece=ece))
    if case.get("reference") is not None and case.get("candidate") is not None:
        results.extend([
            metric("bleu", bleu_score(case["reference"], case["candidate"]), "classic", threshold=0.35),
            metric("rouge_l", rouge_l(case["reference"], case["candidate"]), "classic", threshold=0.5),
        ])
    outputs = case.get("self_consistency_outputs", [])
    if outputs:
        results.append(metric("self_consistency", self_consistency(outputs), "robustness", threshold=0.7, samples=len(outputs)))
    refinements = case.get("refinement_scores", [])
    if len(refinements) >= 2:
        base, final = refinements[0], refinements[-1]
        improvement = clamp((final - base) / max(1e-9, 1.0 - base)) if final >= base else 0.0
        results.append(metric("self_refine_improvement_rate", improvement, "robustness", threshold=0.0, initial=base, final=final))
        detections = case.get("detected_errors", 0)
        total_errors = case.get("known_errors", 0)
        results.append(metric("self_refine_error_detection_rate", safe_div(detections, total_errors), "robustness", threshold=0.8, detected=detections, known=total_errors))
    folds = case.get("cross_validation_scores", [])
    if folds:
        results.append(metric("cross_validation_mean", mean(folds), "classic", threshold=case.get("cv_threshold", 0.75), std=pstdev(folds) if len(folds) > 1 else 0.0, folds=len(folds)))
    benchmarks = case.get("benchmark_scores", {})
    if benchmarks:
        values = list(benchmarks.values())
        results.append(metric("benchmark_score", mean(values), "classic", threshold=case.get("benchmark_threshold", 0.75), candidates=benchmarks))
    return results
