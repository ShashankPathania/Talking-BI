import duckdb
from pathlib import Path
from typing import Optional
import pandas as pd
from app.core.config import settings

class DuckDBStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (settings.dataset_store_path / "talking_bi.duckdb")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # We maintain a persistent connection
        self.conn = duckdb.connect(str(self.db_path))

    def ingest_dataframe(self, table_name: str, df: pd.DataFrame):
        """Standard namespaced ingestion of a dataframe."""
        # Using DuckDB's native dataframe registration
        self.conn.execute(f"CREATE OR REPLACE TABLE \"{table_name}\" AS SELECT * FROM df")

    def execute_query(self, sql: str) -> pd.DataFrame:
        """Execute a query and return a pandas result."""
        # Note: We should add row limit enforcement in the tool layer, 
        # but the store is a lower-level wrapper.
        return self.conn.execute(sql).df()

    def get_schema(self, table_name: str) -> dict[str, str]:
        """Fetch column names and types for a table."""
        res = self.conn.execute(f"DESCRIBE \"{table_name}\"").fetchall()
        # DESCRIBE returns: column_name, column_type, null, key, default, extra
        return {row[0]: str(row[1]) for row in res}

    def table_exists(self, table_name: str) -> bool:
        """Check if a namespaced table exists."""
        res = self.conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", 
            [table_name]
        ).fetchone()
        return res[0] > 0 if res else False

    def close(self):
        self.conn.close()
