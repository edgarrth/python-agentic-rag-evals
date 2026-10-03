from __future__ import annotations

import math
from statistics import mean
from typing import Any

from pe.axiz.payments_evals_lab.evals.common import clamp, harmonic, metric, safe_div
from pe.axiz.payments_evals_lab.rag.embeddings import cosine_similarity


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, ref in enumerate(reference, start=1):
        current = [i]
        for j, hyp in enumerate(hypothesis, start=1):
            substitution = previous[j - 1] + (ref != hyp)
            insertion = current[j - 1] + 1
            deletion = previous[j] + 1
            current.append(min(substitution, insertion, deletion))
        previous = current
    return previous[-1]


def wer(reference: str, hypothesis: str) -> float:
    ref = reference.casefold().split()
    hyp = hypothesis.casefold().split()
    return safe_div(edit_distance(ref, hyp), len(ref)) if ref else (0.0 if not hyp else 1.0)


def boundary_f1(expected: list[float], actual: list[float], tolerance_ms: float = 120.0) -> float:
    matched: set[int] = set()
    tp = 0
    for target in expected:
        candidates = [(abs(target - value), index) for index, value in enumerate(actual) if index not in matched]
        if candidates:
            distance, index = min(candidates)
            if distance <= tolerance_ms:
                matched.add(index)
                tp += 1
    precision = safe_div(tp, len(actual)) if actual else (1.0 if not expected else 0.0)
    recall = safe_div(tp, len(expected)) if expected else 1.0
    return harmonic(precision, recall)


def diarization_error_rate(expected: list[str], actual: list[str]) -> float:
    total = max(len(expected), len(actual))
    if total == 0:
        return 0.0
    mismatches = sum(1 for e, a in zip(expected, actual, strict=False) if e != a) + abs(len(expected) - len(actual))
    return safe_div(mismatches, total)


def evaluate_voice(case: dict[str, Any]) -> list:
    reference = case.get("reference_transcript", "")
    hypothesis = case.get("hypothesis_transcript", "")
    base_wer = wer(reference, hypothesis)
    noise_wers = [wer(item["reference"], item["hypothesis"]) for item in case.get("noise_stress_samples", [])]
    accent_wers = [wer(item["reference"], item["hypothesis"]) for item in case.get("accent_samples", [])]
    vocabulary = case.get("vocabulary", [])
    vocab_hits = sum(1 for term in vocabulary if term.casefold() in hypothesis.casefold())
    vocabulary_accuracy = safe_div(vocab_hits, len(vocabulary)) if vocabulary else 1.0

    stt_latency = float(case.get("stt_latency_ms", 0.0))
    stt_budget = float(case.get("stt_latency_budget_ms", 650.0))
    stt_latency_score = 1.0 if stt_latency <= stt_budget else clamp(stt_budget / max(stt_latency, 1e-9))

    boundaries = boundary_f1(case.get("expected_boundaries_ms", []), case.get("actual_boundaries_ms", []))
    der = diarization_error_rate(case.get("expected_speakers", []), case.get("actual_speakers", []))
    diarization_score = clamp(1.0 - der)

    mos_values = [float(v) for v in case.get("mos_ratings", [])]
    mos = mean(mos_values) if mos_values else 5.0
    mos_score = clamp((mos - 1.0) / 4.0)

    expected_pauses = case.get("expected_pause_ms", [])
    actual_pauses = case.get("actual_pause_ms", [])
    pause_errors = [abs(e - a) / max(e, 1.0) for e, a in zip(expected_pauses, actual_pauses, strict=False)]
    prosody_score = clamp(1.0 - (mean(pause_errors) if pause_errors else 0.0))

    pronunciation = case.get("pronunciation_results", [])
    pronunciation_accuracy = safe_div(sum(1 for item in pronunciation if item.get("correct")), len(pronunciation)) if pronunciation else 1.0

    audio_duration = float(case.get("audio_duration_seconds", 1.0))
    processing = float(case.get("processing_seconds", audio_duration))
    rtf = safe_div(processing, audio_duration)
    rtf_score = 1.0 if rtf <= 1.0 else clamp(1.0 / rtf)
    ttfc = float(case.get("ttfc_ms", 0.0))
    ttfc_budget = float(case.get("ttfc_budget_ms", 500.0))
    ttfc_score = 1.0 if ttfc <= ttfc_budget else clamp(ttfc_budget / max(ttfc, 1e-9))

    expected_embedding = [float(v) for v in case.get("expected_speaker_embedding", [])]
    actual_embedding = [float(v) for v in case.get("actual_speaker_embedding", [])]
    cloning = clamp((cosine_similarity(expected_embedding, actual_embedding) + 1.0) / 2.0) if expected_embedding and actual_embedding else 1.0

    multilingual = case.get("multilingual_results", [])
    multilingual_score = safe_div(sum(1 for item in multilingual if item.get("passed")), len(multilingual)) if multilingual else 1.0

    barge = case.get("barge_in", {})
    barge_success = float(barge.get("success", True))
    barge_latency = float(barge.get("latency_ms", 0.0))
    barge_budget = float(barge.get("budget_ms", 250.0))
    barge_latency_score = 1.0 if barge_latency <= barge_budget else clamp(barge_budget / max(barge_latency, 1e-9))
    barge_score = barge_success * barge_latency_score

    fallback = case.get("fallback", {})
    fallback_score = 1.0 if fallback.get("expected") == fallback.get("actual") else 0.0
    flow = case.get("conversation_flow", [])
    flow_score = safe_div(sum(1 for item in flow if item.get("expected") == item.get("actual")), len(flow)) if flow else 1.0

    return [
        metric("wer", 1.0 - clamp(base_wer), "voice_stt", threshold=0.9, raw_wer=base_wer),
        metric("noise_stress_wer", 1.0 - clamp(mean(noise_wers) if noise_wers else 0.0), "voice_stt", threshold=0.8, mean_wer=mean(noise_wers) if noise_wers else 0.0),
        metric("accent_dialect_wer", 1.0 - clamp(mean(accent_wers) if accent_wers else 0.0), "voice_stt", threshold=0.8, mean_wer=mean(accent_wers) if accent_wers else 0.0),
        metric("stt_latency", stt_latency_score, "voice_stt", threshold=1.0, latency_ms=stt_latency, budget_ms=stt_budget),
        metric("vocabulary_accuracy", vocabulary_accuracy, "voice_stt", threshold=0.9),
        metric("segmentation_boundary_f1", boundaries, "voice_stt", threshold=0.85),
        metric("diarization", diarization_score, "voice_stt", threshold=0.9, diarization_error_rate=der),
        metric("mos", mos_score, "voice_tts", threshold=0.75, mean_opinion_score=mos),
        metric("prosody_rhythm", prosody_score, "voice_tts", threshold=0.8),
        metric("pronunciation_accuracy", pronunciation_accuracy, "voice_tts", threshold=0.9),
        metric("rtf", rtf_score, "voice_performance", threshold=1.0, real_time_factor=rtf),
        metric("ttfc", ttfc_score, "voice_performance", threshold=1.0, ttfc_ms=ttfc, budget_ms=ttfc_budget),
        metric("voice_cloning_fidelity", cloning, "voice_tts", threshold=0.9),
        metric("multilingual_accent_robustness", multilingual_score, "voice_tts", threshold=0.9),
        metric("barge_in", barge_score, "voice_conversation", threshold=0.9, latency_ms=barge_latency),
        metric("voice_fallback", fallback_score, "voice_conversation", threshold=1.0),
        metric("voice_flow_consistency", flow_score, "voice_conversation", threshold=0.9),
    ]
