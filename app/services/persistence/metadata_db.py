import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Any
from app.core.config import settings
from app.core.dataset import DatasetProfile

class MetadataStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (settings.dataset_store_path / "metadata.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS datasets (
                    dataset_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    profile_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS query_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id TEXT,
                    query TEXT,
                    steps_json TEXT,
                    final_response TEXT,
                    latency_ms INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def save_dataset(self, profile: DatasetProfile):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO datasets (dataset_id, name, source_type, profile_json) VALUES (?, ?, ?, ?)",
                (profile.dataset_id, profile.name, profile.source_type, profile.model_dump_json(by_alias=True))
            )

    def get_dataset(self, dataset_id: str) -> Optional[DatasetProfile]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT profile_json FROM datasets WHERE dataset_id = ?", 
                (dataset_id,)
            ).fetchone()
            if row:
                return DatasetProfile.model_validate_json(row[0])
        return None

    def list_datasets(self) -> List[DatasetProfile]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT profile_json FROM datasets ORDER BY created_at DESC").fetchall()
            return [DatasetProfile.model_validate_json(row[0]) for row in rows]

    def log_query(self, dataset_id: str, query: str, steps: list, response: str, latency: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO query_logs (dataset_id, query, steps_json, final_response, latency_ms) VALUES (?, ?, ?, ?, ?)",
                (dataset_id, query, json.dumps(steps), response, latency)
            )
