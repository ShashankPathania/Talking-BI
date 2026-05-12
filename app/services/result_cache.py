"""File-backed query result cache keyed by query-state fingerprints."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.state import QueryResult, QueryState


class ResultCache:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.result_cache_path
        self.root.mkdir(parents=True, exist_ok=True)

    def make_key(self, state: QueryState, execution_mode: str) -> str:
        payload = {
            "execution_mode": execution_mode,
            "intent": {
                "goal": state.intent.goal,
            },
            "data": {
                "source_type": state.data.source_type,
                "source_id": state.data.source_id,
                "table_name": state.data.table_name,
                "schema": state.data.schema_map,
            },
            "transformation": state.transformation.model_dump(),
            "analysis": state.analysis.model_dump(),
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    async def get(self, key: str) -> QueryResult | None:
        path = self.root / f"{key}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return QueryResult.model_validate(payload)

    async def set(self, key: str, result: QueryResult) -> None:
        path = self.root / f"{key}.json"
        payload = self._make_json_safe(result.model_dump(by_alias=True))
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

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
