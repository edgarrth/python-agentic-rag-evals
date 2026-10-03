from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from pe.axiz.payments_evals_lab.config.settings import Settings
from pe.axiz.payments_evals_lab.domain.models import GenerationProvider, RagStrategy
from pe.axiz.payments_evals_lab.services.container import get_container


STRATEGIES = [
    RagStrategy.NATIVE,
    RagStrategy.HYBRID,
    RagStrategy.GRAPHRAG,
    RagStrategy.RAGLIGHT,
    RagStrategy.LIGHTRAG,
]


async def main() -> None:
    container = get_container()
    settings: Settings = container.settings
    provider = GenerationProvider(os.getenv("TEST_GENERATION_PROVIDER", "deterministic"))
    model = os.getenv("TEST_MODEL", settings.openai_model if provider == GenerationProvider.OPENAI else "deterministic")
    prompt_version = os.getenv("TEST_PROMPT_VERSION", "v1")
    top_k = int(os.getenv("TEST_TOP_K", "5"))

    full_metrics, full_gates, full_failures, full_aggregate = await container.eval_runner.run(
        "full",
        RagStrategy.AUTO,
        external_judges=False,
        generation_provider=provider,
        model=model,
        prompt_version=prompt_version,
        top_k=top_k,
    )
    matrix: dict[str, dict] = {}
    for strategy in STRATEGIES:
        metrics, gates, failures, aggregate = await container.eval_runner.run(
            "rag",
            strategy,
            external_judges=False,
            generation_provider=provider,
            model=model,
            prompt_version=prompt_version,
            top_k=top_k,
        )
        scores: dict[str, list[float]] = {}
        latencies = []
        for item in metrics:
            if item.score is not None:
                scores.setdefault(item.metric, []).append(item.score)
            if item.latency_ms is not None:
                latencies.append(item.latency_ms)
        matrix[strategy.value] = {
            "metric_count": len(metrics),
            "gates_passed": gates,
            "gate_failures": failures,
            "aggregate": aggregate,
            "metrics": {name: sum(values) / len(values) for name, values in sorted(scores.items())},
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
        }

    output = {
        "runtime": {
            "generation_provider": provider.value,
            "model": model,
            "prompt_version": prompt_version,
            "top_k": top_k,
            "external_judges": False,
        },
        "full": {
            "metric_count": len(full_metrics),
            "gates_passed": full_gates,
            "gate_failures": full_failures,
            "aggregate": full_aggregate,
        },
        "rag_benchmark": matrix,
    }
    Path(".runtime").mkdir(exist_ok=True)
    target = Path(".runtime/evals-matrix.json")
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if not full_metrics:
        raise SystemExit("La suite full no produjo métricas")
    if set(matrix) != {item.value for item in STRATEGIES}:
        raise SystemExit("El benchmark no cubrió las cinco estrategias RAG")


if __name__ == "__main__":
    asyncio.run(main())
