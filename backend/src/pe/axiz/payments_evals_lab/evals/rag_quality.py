from __future__ import annotations

import re
from typing import Any

from pe.axiz.payments_evals_lab.evals.common import clamp, metric, normalized_contains, safe_div, text_similarity, token_jaccard


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]


def faithfulness(answer: str, contexts: list[str]) -> float:
    if not answer:
        return 0.0
    context_text = " ".join(contexts)
    claims = _sentences(answer)
    if not claims:
        return 0.0
    supported = [max(token_jaccard(claim, context_text), text_similarity(claim, context_text)) for claim in claims]
    return clamp(sum(1 for score in supported if score >= 0.42) / len(supported))


def factual_correctness(answer: str, required_facts: list[str]) -> float:
    if not required_facts:
        return 1.0
    hits = 0
    for fact in required_facts:
        alternatives = [part.strip() for part in str(fact).split("|")]
        if any(normalized_contains(answer, alt) for alt in alternatives):
            hits += 1
    return safe_div(hits, len(required_facts))


def hallucination_rate(answer: str, contexts: list[str], expected_answer: str = "") -> float:
    base = " ".join(contexts) + " " + expected_answer
    claims = _sentences(answer)
    if not claims:
        return 0.0
    unsupported = sum(1 for claim in claims if max(token_jaccard(claim, base), text_similarity(claim, base)) < 0.36)
    return safe_div(unsupported, len(claims))


def evaluate_rag_generation(case: dict[str, Any]) -> list:
    answer = case.get("actual_answer", "")
    expected = case.get("expected_answer", "")
    contexts = case.get("contexts", [])
    required = case.get("required_facts", [])
    faith = faithfulness(answer, contexts)
    correct = factual_correctness(answer, required)
    relevancy = text_similarity(case.get("question", ""), answer)
    grounded = faith
    hallucination = hallucination_rate(answer, contexts, expected)
    semantic = text_similarity(expected, answer) if expected else relevancy
    truthfulness = clamp(1.0 - hallucination)
    coherence = 1.0 if len(_sentences(answer)) <= 1 else sum(token_jaccard(a, b) for a, b in zip(_sentences(answer), _sentences(answer)[1:])) / max(1, len(_sentences(answer)) - 1)
    coherence = clamp(0.5 + coherence / 2.0)
    return [
        metric("faithfulness", faith, "rag_generation", framework="deepeval-ragas-compatible", threshold=0.9),
        metric("groundedness", grounded, "rag_generation", framework="ragas-compatible", threshold=0.9),
        metric("answer_relevancy", relevancy, "rag_generation", framework="deepeval-ragas-compatible", threshold=0.75),
        metric("correctness", correct, "rag_generation", framework="deepeval-compatible", threshold=0.85),
        metric("hallucination", 1.0 - hallucination, "rag_generation", framework="deepeval-compatible", threshold=0.9, hallucination_rate=hallucination),
        metric("semantic_similarity", semantic, "prompt", threshold=0.72),
        metric("truthfulness", truthfulness, "rag_generation", threshold=0.9),
        metric("coherence", coherence, "rag_generation", threshold=0.75),
    ]
