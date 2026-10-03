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
