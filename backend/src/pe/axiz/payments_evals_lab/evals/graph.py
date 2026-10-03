from __future__ import annotations

from typing import Any

from pe.axiz.payments_evals_lab.evals.common import harmonic, metric, safe_div


def prf(expected: set[str], actual: set[str]) -> tuple[float, float, float]:
    tp = len(expected & actual)
    precision = safe_div(tp, len(actual)) if actual else (1.0 if not expected else 0.0)
    recall = safe_div(tp, len(expected)) if expected else 1.0
    return precision, recall, harmonic(precision, recall)


def _rel_key(row: dict[str, str]) -> str:
    return f"{row.get('source','')}|{row.get('relationship','')}|{row.get('target','')}".casefold()


def evaluate_graph(case: dict[str, Any]) -> list:
    ep, er, ef = prf(set(case.get("expected_entities", [])), set(case.get("actual_entities", [])))
    expected_rel = {_rel_key(row) for row in case.get("expected_relationships", [])}
    actual_rel = {_rel_key(row) for row in case.get("actual_relationships", [])}
    rp, rr, rf = prf(expected_rel, actual_rel)
    required_hops = set(case.get("required_evidence_hops", []))
    actual_hops = set(case.get("actual_evidence_hops", []))
    hop_coverage = safe_div(len(required_hops & actual_hops), len(required_hops)) if required_hops else 1.0
    expected_depth = case.get("expected_max_depth", 1)
    actual_depth = case.get("actual_depth", expected_depth)
    depth_score = 1.0 if actual_depth <= expected_depth else max(0.0, 1.0 - (actual_depth - expected_depth) * 0.25)
    graph_accuracy = (ef + rf + hop_coverage) / 3.0
    return [
        metric("entity_precision", ep, "graph", threshold=0.9),
        metric("entity_recall", er, "graph", threshold=0.9),
        metric("entity_f1", ef, "graph", threshold=0.9),
        metric("relationship_precision", rp, "graph", threshold=0.85),
        metric("relationship_recall", rr, "graph", threshold=0.85),
        metric("relationship_f1", rf, "graph", threshold=0.85),
        metric("graph_retrieval_accuracy", graph_accuracy, "graph", threshold=0.85),
        metric("multi_hop_evidence_coverage", hop_coverage, "graph", threshold=0.9),
        metric("graph_depth_correctness", depth_score, "graph", threshold=0.8, expected_depth=expected_depth, actual_depth=actual_depth),
    ]
