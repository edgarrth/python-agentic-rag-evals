from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from pe.axiz.payments_evals_lab.domain.models import MetricResult
from pe.axiz.payments_evals_lab.rag.embeddings import HashingEmbedding, cosine_similarity, tokenize


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            rows.append(json.loads(line))
    return rows


def safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def harmonic(a: float, b: float) -> float:
    return safe_div(2 * a * b, a + b)


def text_similarity(a: str, b: str, dimensions: int = 384) -> float:
    embedder = HashingEmbedding(dimensions)
    return clamp((cosine_similarity(embedder.encode(a), embedder.encode(b)) + 1.0) / 2.0)


def token_jaccard(a: str, b: str) -> float:
    sa, sb = set(tokenize(a)), set(tokenize(b))
    return safe_div(len(sa & sb), len(sa | sb)) if sa or sb else 1.0


def normalized_contains(text: str, phrase: str) -> bool:
    def normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value.casefold()).strip()
    return normalize(phrase) in normalize(text)


def metric(
    name: str,
    score: float | None,
    dimension: str,
    framework: str = "custom",
    threshold: float | None = None,
    reason: str = "",
    **details: Any,
) -> MetricResult:
    passed = None if score is None or threshold is None else score >= threshold
    return MetricResult(
        metric=name,
        framework=framework,
        dimension=dimension,
        score=None if score is None else float(score),
        threshold=threshold,
        passed=passed,
        reason=reason,
        details=details,
    )


def aggregate_scores(results: Iterable[MetricResult]) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for result in results:
        if result.score is not None:
            grouped.setdefault(result.dimension, []).append(result.score)
    return {dimension: mean(values) for dimension, values in grouped.items() if values}


def binary_counts(y_true: list[int], y_pred: list[int]) -> tuple[int, int, int, int]:
    tp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 0 and p == 0)
    return tp, fp, fn, tn


def classification_summary(y_true: list[str], y_pred: list[str]) -> dict[str, Any]:
    labels = sorted(set(y_true) | set(y_pred))
    matrix = {actual: {pred: 0 for pred in labels} for actual in labels}
    for actual, predicted in zip(y_true, y_pred, strict=True):
        matrix[actual][predicted] += 1
    per_label: dict[str, dict[str, float]] = {}
    for label in labels:
        tp = matrix[label][label]
        fp = sum(matrix[other][label] for other in labels if other != label)
        fn = sum(matrix[label][other] for other in labels if other != label)
        precision = safe_div(tp, tp + fp)
        recall = safe_div(tp, tp + fn)
        per_label[label] = {"precision": precision, "recall": recall, "f1": harmonic(precision, recall)}
    accuracy = safe_div(sum(matrix[label][label] for label in labels), len(y_true))
    return {
        "accuracy": accuracy,
        "precision_macro": mean(v["precision"] for v in per_label.values()) if per_label else 0.0,
        "recall_macro": mean(v["recall"] for v in per_label.values()) if per_label else 0.0,
        "f1_macro": mean(v["f1"] for v in per_label.values()) if per_label else 0.0,
        "confusion_matrix": matrix,
        "per_label": per_label,
    }


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = (len(ordered) - 1) * p
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - idx) + ordered[hi] * (idx - lo)
