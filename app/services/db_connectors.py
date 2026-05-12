"""Dialect-aware database connector helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


@dataclass
class DatabaseSchemaSnapshot:
    schema_map: dict[str, str]
    row_count: int
    sample_rows: list[dict[str, Any]]


class DatabaseConnector:
    SUPPORTED_DIALECTS = {"sqlite", "postgresql", "mysql"}

    def validate_url(self, dialect: str, database_url: str) -> None:
        if dialect not in self.SUPPORTED_DIALECTS:
            raise ValueError(f"Unsupported database dialect '{dialect}'.")

        expected_prefixes = {
            "sqlite": "sqlite:///",
            "postgresql": ("postgresql://", "postgresql+psycopg://"),
            "mysql": ("mysql://", "mysql+pymysql://"),
        }
        prefixes = expected_prefixes[dialect]
        if isinstance(prefixes, tuple):
            if not any(database_url.startswith(prefix) for prefix in prefixes):
                raise ValueError(f"{dialect} database_url must start with one of: {', '.join(prefixes)}")
        elif not database_url.startswith(prefixes):
            raise ValueError(f"{dialect} database_url must start with {prefixes}")

    def inspect_table(
        self,
        dialect: str,
        database_url: str,
        table_name: str,
    ) -> DatabaseSchemaSnapshot:
        self.validate_url(dialect, database_url)
        engine = self._create_engine(dialect, database_url)
        try:
            inspector = inspect(engine)
            table_names = inspector.get_table_names()
            if table_name not in table_names:
                raise ValueError(f"Table '{table_name}' was not found in the database.")

            columns = inspector.get_columns(table_name)
            schema_map = {column["name"]: str(column["type"]) for column in columns}
            quoted_table = self._quote_identifier(dialect, table_name)
            with engine.connect() as connection:
                row_count = connection.execute(text(f"SELECT COUNT(*) FROM {quoted_table}")).scalar_one()
                sample_df = pd.read_sql_query(text(f"SELECT * FROM {quoted_table} LIMIT 3"), connection)
                
            # Convert sample rows to native Python types for JSON serialization
            sample_rows = [
                {k: str(v) if pd.notnull(v) else None for k, v in row.items()}
                for row in sample_df.to_dict(orient="records")
            ]
            return DatabaseSchemaSnapshot(schema_map=schema_map, row_count=int(row_count), sample_rows=sample_rows)
        except SQLAlchemyError as exc:
            raise ValueError(f"Database introspection failed: {exc}") from exc
        finally:
            engine.dispose()

    def load_table(
        self,
        dialect: str,
        database_url: str,
        table_name: str,
    ) -> pd.DataFrame:
        self.validate_url(dialect, database_url)
        engine = self._create_engine(dialect, database_url)
        try:
            quoted_table = self._quote_identifier(dialect, table_name)
            with engine.connect() as connection:
                return pd.read_sql_query(text(f"SELECT * FROM {quoted_table}"), connection)
        except SQLAlchemyError as exc:
            raise ValueError(f"Unable to read table '{table_name}': {exc}") from exc
        finally:
            engine.dispose()

    def execute_query(
        self,
        dialect: str,
        database_url: str,
        sql: str,
    ) -> pd.DataFrame:
        self.validate_url(dialect, database_url)
        engine = self._create_engine(dialect, database_url)
        try:
            with engine.connect() as connection:
                return pd.read_sql_query(text(sql), connection)
        except SQLAlchemyError as exc:
            raise ValueError(f"Database query failed: {exc}") from exc
        finally:
            engine.dispose()

    @staticmethod
    def _normalize_url(dialect: str, database_url: str) -> str:
        if dialect == "mysql" and database_url.startswith("mysql://"):
            return database_url.replace("mysql://", "mysql+pymysql://", 1)
        if dialect == "postgresql" and database_url.startswith("postgresql://"):
            return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return database_url

    @classmethod
    def _create_engine(cls, dialect: str, database_url: str) -> Engine:
        normalized_url = cls._normalize_url(dialect, database_url)
        return create_engine(normalized_url, future=True)

    @staticmethod
    def _quote_identifier(dialect: str, identifier: str) -> str:
        escaped = identifier.replace("`", "``").replace('"', '""')
        if dialect == "mysql":
            return f"`{escaped.replace('\"', '')}`"
        return f'"{escaped.replace("`", "")}"'
