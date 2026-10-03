from pathlib import Path

import pytest

from pe.axiz.payments_evals_lab.config.settings import Settings
from pe.axiz.payments_evals_lab.services.generation import GenerationService


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "model": "gpt-test",
            "output": [{"content": [{"type": "output_text", "text": "Respuesta OpenAI simulada"}]}],
            "usage": {"input_tokens": 21, "output_tokens": 7},
        }


class _FakeClient:
    last_url = ""
    last_payload: dict = {}

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, headers: dict, json: dict):
        self.__class__.last_url = url
        self.__class__.last_payload = json
        return _FakeResponse()


@pytest.mark.asyncio
async def test_openai_provider_uses_responses_api_and_selected_model(monkeypatch) -> None:
    settings = Settings(
        datasets_dir=Path("datasets"),
        openai_api_key="test-key",
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-test",
        openai_models="gpt-test",
    )
    service = GenerationService(settings)
    monkeypatch.setattr("pe.axiz.payments_evals_lab.services.generation.httpx.AsyncClient", _FakeClient)

    result = await service.generate(
        question="Explica TX-1007",
        transaction=None,
        code_detail=None,
        contexts=[],
        draft=None,
        provider="openai",
        model="gpt-test",
        prompt_version="v1",
    )

    assert _FakeClient.last_url == "https://api.openai.com/v1/responses"
    assert _FakeClient.last_payload["model"] == "gpt-test"
    assert result.provider == "openai"
    assert result.model == "gpt-test"
    assert result.text == "Respuesta OpenAI simulada"
    assert result.input_tokens == 21
    assert result.output_tokens == 7
