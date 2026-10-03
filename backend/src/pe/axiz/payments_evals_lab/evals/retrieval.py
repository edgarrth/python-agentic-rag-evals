from __future__ import annotations

import math
from typing import Any

from pe.axiz.payments_evals_lab.evals.common import metric, safe_div


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    seen: set[str] = set()
    hits = 0
    for item in retrieved[:k]:
        if item in relevant and item not in seen:
            hits += 1
            seen.add(item)
    return safe_div(hits, k)


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    hits = set(retrieved[:k]) & relevant
    return safe_div(len(hits), len(relevant))


def hit_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    return 1.0 if any(item in relevant for item in retrieved[:k]) else 0.0


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    for index, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1.0 / index
    return 0.0


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    seen: set[str] = set()
    dcg = 0.0
    for index, item in enumerate(retrieved[:k], start=1):
        gain = 1.0 if item in relevant and item not in seen else 0.0
        if gain:
            seen.add(item)
        dcg += gain / math.log2(index + 1)
    ideal_hits = min(k, len(relevant))
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return safe_div(dcg, idcg)


def context_relevancy(retrieved: list[str], relevant: set[str]) -> float:
    return safe_div(len(set(retrieved) & relevant), len(set(retrieved))) if retrieved else 0.0


def context_precision_ranked(retrieved: list[str], relevant: set[str]) -> float:
    relevant_seen = 0
    seen: set[str] = set()
    contributions = []
    for index, item in enumerate(retrieved, start=1):
        if item in relevant and item not in seen:
            seen.add(item)
            relevant_seen += 1
            contributions.append(relevant_seen / index)
    return safe_div(sum(contributions), min(len(relevant), len(retrieved))) if relevant else 1.0


def evaluate_retrieval(case: dict[str, Any], k_values: tuple[int, ...] = (1, 3, 5)) -> list:
    retrieved = case.get("retrieved_sources", [])
    relevant = set(case.get("expected_sources", []))
    results = []
    for k in k_values:
        results.extend([
            metric(f"hit@{k}", hit_at_k(retrieved, relevant, k), "retrieval", threshold=0.8),
            metric(f"precision@{k}", precision_at_k(retrieved, relevant, k), "retrieval", threshold=0.5 if k > 1 else 0.8),
            metric(f"recall@{k}", recall_at_k(retrieved, relevant, k), "retrieval", threshold=0.8),
            metric(f"ndcg@{k}", ndcg_at_k(retrieved, relevant, k), "retrieval", threshold=0.75),
        ])
    results.append(metric("mrr", reciprocal_rank(retrieved, relevant), "retrieval", threshold=0.8))
    results.append(metric("context_precision", context_precision_ranked(retrieved, relevant), "rag_retrieval", framework="ragas-compatible", threshold=0.8))
    results.append(metric("context_recall", recall_at_k(retrieved, relevant, max(len(retrieved), 1)), "rag_retrieval", framework="ragas-compatible", threshold=0.9))
    results.append(metric("context_relevancy", context_relevancy(retrieved, relevant), "rag_retrieval", framework="ragas-compatible", threshold=0.75))
    raw = case.get("raw_retrieved_sources")
    if raw:
        raw_ndcg = ndcg_at_k(raw, relevant, min(5, len(raw)))
        reranked_ndcg = ndcg_at_k(retrieved, relevant, min(5, len(retrieved)))
        delta = reranked_ndcg - raw_ndcg
        results.append(metric("rerank_ndcg_delta", (delta + 1.0) / 2.0, "retrieval", threshold=0.5, raw_ndcg=raw_ndcg, reranked_ndcg=reranked_ndcg, delta=delta))
    return results
