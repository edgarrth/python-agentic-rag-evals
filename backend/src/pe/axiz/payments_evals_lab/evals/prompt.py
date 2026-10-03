from __future__ import annotations

import json
import re
from statistics import mean
from typing import Any

from jsonschema import Draft202012Validator

from pe.axiz.payments_evals_lab.evals.common import clamp, metric, normalized_contains, safe_div, text_similarity


def evaluate_prompt(case: dict[str, Any]) -> list:
    output = case.get("output", "")
    results = []
    json_obj = None
    json_valid = 0.0
    try:
        json_obj = json.loads(output)
        json_valid = 1.0
    except (json.JSONDecodeError, TypeError):
        pass
    if case.get("require_json") or case.get("json_schema"):
        results.append(metric("json_validity", json_valid, "prompt", framework="promptfoo-compatible", threshold=1.0))
    if case.get("json_schema"):
        schema_valid = 0.0
        errors: list[str] = []
        if json_obj is not None:
            validation_errors = list(Draft202012Validator(case["json_schema"]).iter_errors(json_obj))
            errors = [error.message for error in validation_errors]
            schema_valid = 1.0 if not errors else 0.0
        results.append(metric("json_schema", schema_valid, "prompt", framework="promptfoo-compatible", threshold=1.0, errors=errors))
    for pattern in case.get("regex", []):
        results.append(metric("regex", 1.0 if re.search(pattern, output) else 0.0, "prompt", framework="promptfoo-compatible", threshold=1.0, pattern=pattern))
    for phrase in case.get("contains", []):
        results.append(metric("contains", 1.0 if normalized_contains(output, phrase) else 0.0, "prompt", framework="promptfoo-compatible", threshold=1.0, phrase=phrase))
    for phrase in case.get("not_contains", []):
        results.append(metric("not_contains", 0.0 if normalized_contains(output, phrase) else 1.0, "prompt", framework="promptfoo-compatible", threshold=1.0, phrase=phrase))
    min_len = case.get("min_length")
    max_len = case.get("max_length")
    if min_len is not None or max_len is not None:
        length_ok = (min_len is None or len(output) >= min_len) and (max_len is None or len(output) <= max_len)
        results.append(metric("length_constraint", float(length_ok), "prompt", threshold=1.0, length=len(output), min=min_len, max=max_len))
    if case.get("reference"):
        results.append(metric("semantic_similarity", text_similarity(case["reference"], output), "prompt", framework="promptfoo-compatible", threshold=case.get("similarity_threshold", 0.75)))
    rubric = case.get("rubric_checks", [])
    if rubric:
        checks = [1.0 if normalized_contains(output, item["must_contain"]) else 0.0 for item in rubric]
        results.append(metric("llm_rubric_proxy", mean(checks), "prompt", framework="llm-as-judge-proxy", threshold=0.85, checks=rubric))
    variants = case.get("prompt_variant_outputs", [])
    if variants:
        pair_scores = [text_similarity(variants[0], candidate) for candidate in variants[1:]]
        sensitivity_robustness = mean(pair_scores) if pair_scores else 1.0
        results.append(metric("prompt_sensitivity", sensitivity_robustness, "prompt", threshold=0.8, variation=1.0 - sensitivity_robustness))
    structured = [result for result in results if result.metric in {"json_validity", "json_schema", "regex", "contains", "not_contains", "length_constraint"}]
    if structured:
        pass_rate = safe_div(sum(1 for result in structured if result.score == 1.0), len(structured))
        results.append(metric("structured_output_pass_rate", clamp(pass_rate), "prompt", framework="promptfoo-compatible", threshold=1.0))
    return results
