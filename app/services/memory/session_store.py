"""Simple session store for multi-turn conversations."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.state import QueryState, SessionState


class SessionStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.session_store_path
        self.root.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, SessionState] = {}

    async def get_or_create(self, session_id: str, dataset_id: str | None = None) -> SessionState:
        session = self._sessions.get(session_id) or await self.get(session_id)
        if session is None:
            session = SessionState(
                session_id=session_id,
                dataset_id=dataset_id,
                query_state=QueryState(),
            )
            self._sessions[session_id] = session
        elif dataset_id and session.dataset_id is None:
            session.dataset_id = dataset_id
        return session

    async def save(self, session: SessionState) -> None:
        self._sessions[session.session_id] = session
        path = self.root / f"{session.session_id}.json"
        payload = self._make_json_safe(session.model_dump(by_alias=True))
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    async def get(self, session_id: str) -> SessionState | None:
        session = self._sessions.get(session_id)
        if session is not None:
            return session

        path = self.root / f"{session_id}.json"
        if not path.exists():
            return None

        payload = json.loads(path.read_text(encoding="utf-8"))
        session = SessionState.model_validate(payload)
        self._sessions[session_id] = session
        return session

    async def list_sessions(self) -> list[SessionState]:
        sessions: list[SessionState] = []
        for path in sorted(self.root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            payload = json.loads(path.read_text(encoding="utf-8"))
            session = SessionState.model_validate(payload)
            self._sessions[session.session_id] = session
            sessions.append(session)
        return sessions

    def _make_json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, dict):
            return {
                str(key): self._make_json_safe(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._make_json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [self._make_json_safe(item) for item in value]
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if hasattr(value, "item"):
            return self._make_json_safe(value.item())
        return str(value)
