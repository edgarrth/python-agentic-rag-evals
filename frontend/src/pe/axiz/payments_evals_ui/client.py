from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

import httpx


class BackendClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
        self.timeout = float(os.getenv("UI_BACKEND_TIMEOUT_SECONDS", "60"))

    async def health(self) -> dict:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()

    async def suites(self) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.base_url}/api/v1/evals/suites")
            response.raise_for_status()
            return response.json()

    async def runs(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.base_url}/api/v1/evals/runs")
            response.raise_for_status()
            return response.json()

    async def get_run(self, run_id: str) -> dict:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.base_url}/api/v1/evals/runs/{run_id}")
            response.raise_for_status()
            return response.json()

    async def create_run(self, suite: str, strategy: str = "auto") -> dict:
        payload = {"suite": suite, "strategy": strategy, "candidate": "candidate", "baseline": "baseline", "include_external_judges": False}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(f"{self.base_url}/api/v1/evals/runs", json=payload)
            response.raise_for_status()
            return response.json()

    async def trace(self, trace_id: str) -> dict:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.base_url}/api/v1/traces/{trace_id}")
            response.raise_for_status()
            return response.json()

    async def stream_chat(self, payload: dict) -> AsyncIterator[dict]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, read=self.timeout)) as client:
            async with client.stream("POST", f"{self.base_url}/api/v1/chat/stream", json=payload) as response:
                response.raise_for_status()
                event_name = "message"
                data_lines: list[str] = []
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_name = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line.split(":", 1)[1].strip())
                    elif not line and data_lines:
                        payload_data = json.loads("\n".join(data_lines))
                        yield {"event": event_name, **payload_data}
                        event_name = "message"
                        data_lines = []
