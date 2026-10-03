from __future__ import annotations

from typing import Any

from pe.axiz.payments_evals_lab.evals.common import classification_summary, metric, safe_div


def evaluate_routing(rows: list[dict[str, Any]]) -> list:
    y_true = [row["expected_intent"] for row in rows]
    y_pred = [row["predicted_intent"] for row in rows]
    summary = classification_summary(y_true, y_pred)
    ood_true = [1 if item == "out_of_domain" else 0 for item in y_true]
    ood_pred = [1 if item == "out_of_domain" else 0 for item in y_pred]
    tp = sum(1 for t, p in zip(ood_true, ood_pred, strict=True) if t == p == 1)
    fp = sum(1 for t, p in zip(ood_true, ood_pred, strict=True) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(ood_true, ood_pred, strict=True) if t == 1 and p == 0)
    ood_precision = safe_div(tp, tp + fp)
    ood_recall = safe_div(tp, tp + fn)
    strategy_accuracy = safe_div(sum(1 for row in rows if row.get("expected_strategy") == row.get("predicted_strategy")), len(rows))
    return [
        metric("routing_accuracy", summary["accuracy"], "routing", threshold=0.85, confusion_matrix=summary["confusion_matrix"]),
        metric("routing_precision_macro", summary["precision_macro"], "routing", threshold=0.8, per_label=summary["per_label"]),
        metric("routing_recall_macro", summary["recall_macro"], "routing", threshold=0.8),
        metric("routing_f1_macro", summary["f1_macro"], "routing", threshold=0.8),
        metric("strategy_accuracy", strategy_accuracy, "routing", threshold=0.8),
        metric("ood_precision", ood_precision, "routing", threshold=0.9),
        metric("ood_recall", ood_recall, "routing", threshold=0.9),
    ]
