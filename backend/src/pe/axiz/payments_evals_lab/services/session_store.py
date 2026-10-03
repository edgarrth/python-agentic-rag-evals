from __future__ import annotations

import threading
from collections import OrderedDict
from datetime import UTC, datetime
from uuid import uuid4


class SessionStore:
    def __init__(self, max_sessions: int = 200) -> None:
        self._sessions: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.RLock()
        self._max_sessions = max_sessions

    def get_or_create(self, session_id: str | None) -> dict:
        with self._lock:
            sid = session_id or str(uuid4())
            if sid not in self._sessions:
                self._sessions[sid] = {"session_id": sid, "created_at": datetime.now(UTC).isoformat(), "turns": []}
            self._sessions.move_to_end(sid)
            self._trim()
            return self._sessions[sid]

    def append_turn(self, session_id: str, role: str, content: str, **metadata: object) -> None:
        with self._lock:
            session = self._sessions[session_id]
            session["turns"].append({"role": role, "content": content, "timestamp": datetime.now(UTC).isoformat(), **metadata})

    def get(self, session_id: str) -> dict | None:
        with self._lock:
            return self._sessions.get(session_id)

    def _trim(self) -> None:
        while len(self._sessions) > self._max_sessions:
            self._sessions.popitem(last=False)


session_store = SessionStore()
