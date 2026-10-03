from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from pe.axiz.payments_evals_lab.evals.common import harmonic, metric, normalized_contains, safe_div, text_similarity


def evaluate_agentic(case: dict[str, Any]) -> list:
    required_tools = set(case.get("required_tools", []))
    allowed_tools = set(case.get("allowed_tools", [])) | required_tools
    actual_calls = case.get("tool_calls", [])
    actual_tools = [item.get("tool") for item in actual_calls]
    actual_set = set(actual_tools)

    tp = len(actual_set & required_tools)
    precision = safe_div(len(actual_set & allowed_tools), len(actual_set)) if actual_set else (1.0 if not required_tools else 0.0)
    recall = safe_div(tp, len(required_tools)) if required_tools else 1.0
    tool_f1 = harmonic(precision, recall)
    invalid = sorted(actual_set - allowed_tools)
    missing = sorted(required_tools - actual_set)

    expected_sequence = case.get("expected_tool_sequence", [])
    sequence_valid = 1.0
    if expected_sequence:
        cursor = 0
        for tool in actual_tools:
            if cursor < len(expected_sequence) and tool == expected_sequence[cursor]:
                cursor += 1
        sequence_valid = safe_div(cursor, len(expected_sequence))
    tool_correctness = (precision + recall + sequence_valid) / 3.0

    argument_constraints = case.get("argument_constraints", {})
    schema_valid_count = 0
    value_valid_count = 0
    semantic_scores = []
    evaluated_calls = 0
    violations: list[str] = []
    tool_schemas = case.get("tool_schemas", {})
    for call in actual_calls:
        tool = call.get("tool", "")
        arguments = call.get("arguments", {})
        evaluated_calls += 1
        schema = tool_schemas.get(tool)
        if schema:
            errors = list(Draft202012Validator(schema).iter_errors(arguments))
            schema_ok = not errors
            if not schema_ok:
                violations.extend(f"{tool}: {error.message}" for error in errors)
        else:
            schema_ok = bool(call.get("schema_valid", True))
        schema_valid_count += int(schema_ok)

        relevant_constraints = {key.split(".", 1)[1]: value for key, value in argument_constraints.items() if key.startswith(f"{tool}.")}
        value_ok = all(arguments.get(key) == expected for key, expected in relevant_constraints.items())
        value_valid_count += int(value_ok)
        semantic_reference = case.get("goal", "") + " " + case.get("question", "")
        semantic_scores.append(text_similarity(semantic_reference, " ".join(str(v) for v in arguments.values())))

    if evaluated_calls:
        schema_score = schema_valid_count / evaluated_calls
        value_score = value_valid_count / evaluated_calls
        semantic_score = sum(semantic_scores) / evaluated_calls
    else:
        schema_score = value_score = semantic_score = 1.0 if not required_tools else 0.0
    argument_correctness = (schema_score + value_score + semantic_score) / 3.0

    completion_criteria = case.get("completion_criteria", [])
    observed = set(case.get("completed_criteria", []))
    deterministic_completion = safe_div(len(observed & set(completion_criteria)), len(completion_criteria)) if completion_criteria else 1.0
    semantic_completion = text_similarity(case.get("goal", ""), case.get("actual_answer", "")) if case.get("goal") else deterministic_completion
    task_completion = 0.95 * deterministic_completion + 0.05 * semantic_completion

    turn_scores = []
    for turn in case.get("turns", []):
        if turn.get("role") == "assistant":
            turn_scores.append(text_similarity(turn.get("expected_intent", case.get("goal", "")), turn.get("content", "")))
    turn_relevancy = sum(turn_scores) / len(turn_scores) if turn_scores else text_similarity(case.get("question", ""), case.get("actual_answer", ""))

    requirements = case.get("conversation_requirements", completion_criteria)
    answer = case.get("actual_answer", "")
    covered = sum(1 for requirement in requirements if normalized_contains(answer, requirement) or requirement in observed)
    conversation_completeness = safe_div(covered, len(requirements)) if requirements else 1.0

    return [
        metric("task_completion", task_completion, "agentic", framework="deepeval-compatible", threshold=0.95, deterministic=deterministic_completion, semantic=semantic_completion),
        metric("tool_correctness", tool_correctness, "agentic", framework="deepeval-compatible", threshold=0.95, precision=precision, recall=recall, f1=tool_f1, sequence_validity=sequence_valid, missing=missing, invalid=invalid),
        metric("tool_precision", precision, "agentic", threshold=0.95),
        metric("tool_recall", recall, "agentic", threshold=0.95),
        metric("tool_f1", tool_f1, "agentic", threshold=0.95),
        metric("tool_sequence_validity", sequence_valid, "agentic", threshold=0.9),
        metric("argument_correctness", argument_correctness, "agentic", framework="deepeval-compatible", threshold=0.9, schema=schema_score, values=value_score, semantic=semantic_score, violations=violations),
        metric("argument_schema_validity", schema_score, "agentic", threshold=1.0),
        metric("argument_value_validity", value_score, "agentic", threshold=0.95),
        metric("argument_semantic_correctness", semantic_score, "agentic", threshold=0.65),
        metric("turn_relevancy", turn_relevancy, "conversation", framework="deepeval-compatible", threshold=0.75),
        metric("conversation_completeness", conversation_completeness, "conversation", framework="deepeval-compatible", threshold=0.9),
    ]
