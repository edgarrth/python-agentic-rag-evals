from __future__ import annotations

import asyncio
import threading
from collections import OrderedDict
from datetime import UTC, datetime
from uuid import uuid4

from pe.axiz.payments_evals_lab.domain.models import EvalRunSummary


class EvalRunStore:
    def __init__(self, max_runs: int = 100) -> None:
        self._runs: OrderedDict[str, EvalRunSummary] = OrderedDict()
        self._events: dict[str, asyncio.Queue[dict]] = {}
        self._lock = threading.RLock()
        self._max_runs = max_runs

    def create(self, suite: str) -> EvalRunSummary:
        run = EvalRunSummary(run_id=str(uuid4()), suite=suite, status="queued", started_at=datetime.now(UTC))
        with self._lock:
            self._runs[run.run_id] = run
            self._events[run.run_id] = asyncio.Queue()
            self._trim()
        return run

    def get(self, run_id: str) -> EvalRunSummary | None:
        with self._lock:
            return self._runs.get(run_id)

    def list(self) -> list[EvalRunSummary]:
        with self._lock:
            return list(reversed(self._runs.values()))

    def update(self, run: EvalRunSummary) -> None:
        with self._lock:
            self._runs[run.run_id] = run

    def queue(self, run_id: str) -> asyncio.Queue[dict] | None:
        return self._events.get(run_id)

    async def publish(self, run_id: str, event: dict) -> None:
        queue = self._events.get(run_id)
        if queue is not None:
            await queue.put(event)

    def _trim(self) -> None:
        while len(self._runs) > self._max_runs:
            old_id, _ = self._runs.popitem(last=False)
            self._events.pop(old_id, None)


eval_run_store = EvalRunStore()
