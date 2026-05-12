import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional, Dict
from app.core.config import settings

class PersistentCache:
    """SQLite-backed persistent cache for tool results and agent state."""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (settings.dataset_store_path / "cache.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    cache_key TEXT PRIMARY KEY,
                    dataset_id TEXT,
                    payload_json TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dataset ON cache(dataset_id)")

    def make_key(self, dataset_id: str, context: Any) -> str:
        """Create a stable hash key from dataset ID and arbitrary context."""
        payload = {
            "dataset_id": dataset_id,
            "context": context
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT payload_json FROM cache WHERE cache_key = ?", (key,)).fetchone()
            if row:
                return json.loads(row[0])
        return None

    def set(self, key: str, dataset_id: str, payload: Any):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (cache_key, dataset_id, payload_json) VALUES (?, ?, ?)",
                (key, dataset_id, json.dumps(payload, default=str))
            )

    def invalidate_dataset(self, dataset_id: str):
        """Clear all cache entries related to a specific dataset."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM cache WHERE dataset_id = ?", (dataset_id,))

    def clear(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM cache")
