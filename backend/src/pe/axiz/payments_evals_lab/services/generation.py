from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from pe.axiz.payments_evals_lab.config.settings import Settings
from pe.axiz.payments_evals_lab.domain.models import RetrievedContext

_TX = re.compile(r"\bTX-[0-9]{4}\b", re.I)


@dataclass(slots=True)
class GenerationResult:
    text: str
    provider: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    raw_usage: dict[str, Any]


class GenerationService:
    """Generación configurable con modo determinista u OpenAI Responses API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.prompts_dir = settings.datasets_dir / "prompts"

    def prompt_versions(self) -> list[str]:
        versions = sorted(path.stem for path in self.prompts_dir.glob("*.md")) if self.prompts_dir.exists() else []
        return versions or ["v1"]

    async def generate(
        self,
        *,
        question: str,
        transaction: dict[str, Any] | None,
        code_detail: dict[str, Any] | None,
        contexts: list[RetrievedContext],
        draft: dict[str, Any] | None,
        provider: str,
        model: str,
        prompt_version: str,
    ) -> GenerationResult:
        normalized_provider = provider.strip().lower() or self.settings.generation_provider
        if normalized_provider == "openai":
            return await self._openai_generate(
                question=question,
                transaction=transaction,
                code_detail=code_detail,
                contexts=contexts,
                draft=draft,
                model=(model if model and model != "deterministic" else self.settings.openai_model),
                prompt_version=prompt_version,
            )
        text = self._deterministic_answer(question, transaction, code_detail, contexts, draft)
        return GenerationResult(
            text=text,
            provider="deterministic",
            model="deterministic",
            prompt_version=prompt_version,
            input_tokens=self._token_count(question) + sum(self._token_count(ctx.text) for ctx in contexts),
            output_tokens=self._token_count(text),
            raw_usage={},
        )

    async def _openai_generate(
        self,
        *,
        question: str,
        transaction: dict[str, Any] | None,
        code_detail: dict[str, Any] | None,
        contexts: list[RetrievedContext],
        draft: dict[str, Any] | None,
        model: str,
        prompt_version: str,
    ) -> GenerationResult:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY es obligatoria cuando GENERATION_PROVIDER=openai")

        instructions = self._load_prompt(prompt_version)
        evidence = {
            "question": question,
            "transaction": transaction,
            "authorization_code": code_detail,
            "retrieval_contexts": [
                {"source": ctx.source, "text": ctx.text, "score": ctx.score, "rank": ctx.rank}
                for ctx in contexts
            ],
            "case_draft": draft,
        }
        payload = {
            "model": model,
            "instructions": instructions,
            "input": (
                "Responde en español y utiliza exclusivamente la evidencia observable siguiente. "
                "Si falta evidencia, indícalo explícitamente.\n\n"
                + json.dumps(evidence, ensure_ascii=False, default=str)
            ),
            "max_output_tokens": 900,
        }
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}", "Content-Type": "application/json"}
        timeout = httpx.Timeout(self.settings.request_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{self.settings.openai_base_url.rstrip('/')}/responses", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        text = self._extract_output_text(data)
        if not text:
            raise RuntimeError("OpenAI Responses API no devolvió texto utilizable")
        usage = data.get("usage") or {}
        return GenerationResult(
            text=text,
            provider="openai",
            model=str(data.get("model") or model),
            prompt_version=prompt_version,
            input_tokens=int(usage.get("input_tokens") or self._token_count(payload["input"])),
            output_tokens=int(usage.get("output_tokens") or self._token_count(text)),
            raw_usage=usage,
        )

    def _load_prompt(self, version: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9._-]", "", version) or "v1"
        path = self.prompts_dir / f"{safe}.md"
        if not path.exists():
            path = self.prompts_dir / "v1.md"
        if not path.exists():
            return (
                "Eres un agente de payment processing. Responde únicamente con evidencia de tools y RAG, "
                "no expongas PII ni secretos y distingue hechos de recomendaciones."
            )
        return path.read_text(encoding="utf-8").strip()

    @staticmethod
    def _extract_output_text(data: dict[str, Any]) -> str:
        direct = data.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        chunks: list[str] = []
        for item in data.get("output", []) or []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []) or []:
                if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                    text = content.get("text")
                    if isinstance(text, str) and text.strip():
                        chunks.append(text.strip())
        return "\n".join(chunks).strip()

    @staticmethod
    def _deterministic_answer(
        question: str,
        transaction: dict[str, Any] | None,
        code_detail: dict[str, Any] | None,
        contexts: list[RetrievedContext],
        draft: dict[str, Any] | None,
    ) -> str:
        parts: list[str] = []
        if transaction and transaction.get("found"):
            parts.append(
                f"La transacción {transaction['transaction_id']} figura como {transaction['status']} por "
                f"{transaction['amount']:.2f} {transaction['currency']}, procesada por {transaction['acquirer']} "
                f"hacia {transaction['issuer']}."
            )
        elif _TX.search(question):
            parts.append("No se encontró la transacción solicitada en el dataset controlado.")

        if code_detail and code_detail.get("found"):
            parts.append(
                f"El código de autorización {code_detail['code']} corresponde a “{code_detail['meaning']}”. "
                f"La acción operativa indicada es: {code_detail['recommended_action']}"
            )
        if contexts:
            sources = ", ".join(dict.fromkeys(ctx.source for ctx in contexts[:3]))
            summary = contexts[0].text.replace("#", "").replace("\n", " ").strip()
            if len(summary) > 420:
                summary = summary[:417].rstrip() + "..."
            parts.append(f"La evidencia recuperada respalda el análisis: {summary}")
            parts.append(f"Fuentes consultadas: {sources}.")
        if draft and draft.get("draft"):
            parts.append(
                f"Se generó el borrador no destructivo {draft['case_id']} con prioridad {draft['priority']}; "
                "no se envió a ningún sistema externo."
            )
        if not parts:
            parts.append(
                "Se recuperó conocimiento de pagos, pero no existe evidencia suficiente para una conclusión más específica "
                "en el dataset controlado."
            )
        return " ".join(parts)

    @staticmethod
    def _token_count(text: str) -> int:
        return max(1, len(text.split()))
