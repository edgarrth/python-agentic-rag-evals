from pathlib import Path

import pytest

from pe.axiz.payments_evals_lab.agent.controller import AgenticController
from pe.axiz.payments_evals_lab.config.settings import Settings
from pe.axiz.payments_evals_lab.domain.models import RagStrategy
from pe.axiz.payments_evals_lab.evals.suite_runner import EvaluationSuiteRunner
from pe.axiz.payments_evals_lab.observability.tracing import TraceStore
from pe.axiz.payments_evals_lab.rag.router import AdaptiveRouter
from pe.axiz.payments_evals_lab.rag.service import RagService
from pe.axiz.payments_evals_lab.repositories.payment_repository import PaymentRepository
from pe.axiz.payments_evals_lab.services.session_store import SessionStore
from pe.axiz.payments_evals_lab.tools.payment_tools import build_tool_registry


EXPECTED = {
    "accuracy", "precision_macro", "recall_macro", "f1_macro", "log_loss", "bleu", "rouge_l", "self_consistency",
    "cross_validation_mean", "benchmark_score", "hit@1", "mrr", "ndcg@5", "precision@5", "recall@5",
    "context_precision", "context_recall", "context_relevancy", "faithfulness", "groundedness", "answer_relevancy",
    "correctness", "hallucination", "task_completion", "tool_correctness", "argument_correctness", "turn_relevancy",
    "conversation_completeness", "routing_accuracy", "routing_f1_macro", "ood_recall", "entity_f1", "relationship_f1",
    "graph_retrieval_accuracy", "json_schema", "regex", "contains", "not_contains", "semantic_similarity",
    "prompt_sensitivity", "toxicity", "bias", "fairness", "pii_leakage", "secret_leakage", "policy_compliance",
    "prompt_injection_resistance", "jailbreak_resistance", "red_team_attack_resistance", "context_retention",
    "reference_resolution", "ambiguity_handling", "fallback_correctness", "retry_correctness", "failure_recovery",
    "graceful_degradation", "retrieval_latency", "generation_latency", "total_latency", "token_budget",
    "estimated_cost_budget", "golden_regression", "baseline_candidate_regression", "data_drift", "concept_drift",
    "wer", "noise_stress_wer", "accent_dialect_wer", "stt_latency", "vocabulary_accuracy", "segmentation_boundary_f1",
    "diarization", "mos", "prosody_rhythm", "pronunciation_accuracy", "rtf", "ttfc", "voice_cloning_fidelity",
    "multilingual_accent_robustness", "barge_in", "voice_fallback", "voice_flow_consistency",
}


@pytest.mark.asyncio
async def test_full_suite_covers_metric_catalog() -> None:
    settings = Settings(datasets_dir=Path("datasets"), eval_judge_enabled=False)
    repo = PaymentRepository(settings.datasets_dir)
    rag = RagService(settings)
    router = AdaptiveRouter()
    tools = build_tool_registry(repo, rag)
    controller = AgenticController(router, tools, rag, TraceStore(), SessionStore())
    runner = EvaluationSuiteRunner(settings, controller, rag, router, tools)

    results, _, _, aggregate = await runner.run("full", RagStrategy.AUTO, external_judges=False)
    names = {item.metric for item in results}
    missing = EXPECTED - names
    assert not missing, sorted(missing)
    assert aggregate
    assert all(item.case_id for item in results)
