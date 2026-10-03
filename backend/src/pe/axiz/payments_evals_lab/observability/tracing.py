from __future__ import annotations

import threading
from collections import OrderedDict
from uuid import uuid4

from pe.axiz.payments_evals_lab.domain.models import ExecutionTrace, TraceEvent, TraceStage


class TraceStore:
    """Almacén acotado de trazas observables; no persiste razonamiento privado."""

    def __init__(self, max_items: int = 500) -> None:
        self._items: OrderedDict[str, ExecutionTrace] = OrderedDict()
        self._lock = threading.RLock()
        self._max_items = max_items

    def create(self, **kwargs: object) -> ExecutionTrace:
        trace = ExecutionTrace(trace_id=str(uuid4()), **kwargs)
        with self._lock:
            self._items[trace.trace_id] = trace
            self._evict()
        return trace

    def append(self, trace_id: str, stage: TraceStage, label: str, detail: str = "", **payload: object) -> None:
        with self._lock:
            trace = self._items[trace_id]
            trace.events.append(TraceEvent(stage=stage, label=label, detail=detail, payload=dict(payload)))

    def put(self, trace: ExecutionTrace) -> None:
        with self._lock:
            self._items[trace.trace_id] = trace
            self._items.move_to_end(trace.trace_id)
            self._evict()

    def get(self, trace_id: str) -> ExecutionTrace | None:
        with self._lock:
            return self._items.get(trace_id)

    def _evict(self) -> None:
        while len(self._items) > self._max_items:
            self._items.popitem(last=False)


trace_store = TraceStore()
