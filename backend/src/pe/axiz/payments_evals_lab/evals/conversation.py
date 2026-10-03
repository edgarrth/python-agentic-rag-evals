from __future__ import annotations

from typing import Any

from pe.axiz.payments_evals_lab.evals.common import metric, normalized_contains, safe_div, text_similarity


def evaluate_conversation(case: dict[str, Any]) -> list:
    turns = case.get("turns", [])
    final = case.get("final_answer", "")
    retained = case.get("must_retain", [])
    references = case.get("reference_expectations", [])
    ambiguity = case.get("ambiguity", {})

    retained_hits = sum(1 for value in retained if normalized_contains(final, value))
    retention = safe_div(retained_hits, len(retained)) if retained else 1.0

    ref_hits = 0
    for item in references:
        if normalized_contains(final, item.get("resolved_value", "")):
            ref_hits += 1
    ref_score = safe_div(ref_hits, len(references)) if references else 1.0

    should_clarify = ambiguity.get("should_clarify", False)
    clarification_markers = ("¿", "aclar", "confirma", "especifica", "cuál", "cual")
    clarified = any(marker in final.casefold() for marker in clarification_markers)
    ambiguity_score = 1.0 if (not should_clarify or clarified) else 0.0

    assistant_turns = [turn for turn in turns if turn.get("role") == "assistant"]
    relevancy_scores = [text_similarity(turn.get("expected_intent", ""), turn.get("content", "")) for turn in assistant_turns if turn.get("expected_intent")]
    turn_relevancy = sum(relevancy_scores) / len(relevancy_scores) if relevancy_scores else 1.0

    requirements = case.get("requirements", [])
    req_hits = sum(1 for item in requirements if normalized_contains(final, item))
    completeness = safe_div(req_hits, len(requirements)) if requirements else 1.0
    return [
        metric("context_retention", retention, "conversation", threshold=0.9),
        metric("reference_resolution", ref_score, "conversation", threshold=0.9),
        metric("ambiguity_handling", ambiguity_score, "conversation", threshold=1.0),
        metric("turn_relevancy", turn_relevancy, "conversation", threshold=0.8),
        metric("conversation_completeness", completeness, "conversation", threshold=0.9),
    ]
