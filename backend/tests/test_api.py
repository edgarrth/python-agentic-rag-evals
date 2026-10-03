from fastapi.testclient import TestClient

from pe.axiz.payments_evals_lab.main import app


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_sse_endpoint() -> None:
    response = client.post(
        "/api/v1/chat/stream",
        json={"question": "Revisa TX-1007 y explica el rechazo", "strategy": "hybrid", "top_k": 5, "include_case_draft": True},
    )
    assert response.status_code == 200
    assert "event: result" in response.text
    assert "TX-1007" in response.text
    assert "event: eof" in response.text


def test_runtime_options_expose_real_execution_modes() -> None:
    response = client.get("/api/v1/runtime/options")
    assert response.status_code == 200
    payload = response.json()
    assert payload["generation_providers"] == ["deterministic", "openai"]
    assert "deterministic" in payload["models"]
    assert "openai" in payload["models"]
    assert "v1" in payload["prompt_versions"]


def test_chat_sse_reports_actual_generation_runtime() -> None:
    response = client.post(
        "/api/v1/chat/stream",
        json={
            "question": "Revisa TX-1007 y explica el rechazo",
            "strategy": "hybrid",
            "top_k": 5,
            "include_case_draft": False,
            "generation_provider": "deterministic",
            "model": "deterministic",
            "prompt_version": "v1",
        },
    )
    assert response.status_code == 200
    assert '"generation_provider": "deterministic"' in response.text
    assert '"model": "deterministic"' in response.text
    assert '"prompt_version": "v1"' in response.text
