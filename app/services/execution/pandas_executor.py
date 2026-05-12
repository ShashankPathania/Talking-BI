"""Pandas execution path for file-backed and demo datasets."""

from __future__ import annotations

import re
import sqlite3

import pandas as pd

from app.core.state import QueryResult, QueryState
from app.services.datasets import DatasetService


class PandasExecutor:
    def __init__(self, dataset_service: DatasetService | None = None) -> None:
        self.dataset_service = dataset_service or DatasetService()

    def execute(self, state: QueryState, sql_override: str | None = None) -> QueryResult:
        frame = self._load_dataframe(state)
        executed_sql = None
        if sql_override:
            transformed, executed_sql = self._execute_sql_over_frame(frame, state, sql_override)
        else:
            transformed = self._apply_transformations(frame, state)
        return QueryResult(
            rows=transformed.to_dict(orient="records"),
            row_count=len(transformed),
            schema={column: str(dtype) for column, dtype in transformed.dtypes.items()},
            execution_mode="pandas",
            generated_sql=sql_override,
            executed_sql=executed_sql,
            profile=self._build_profile(transformed),
        )

    def _load_dataframe(self, state: QueryState) -> pd.DataFrame:
        if state.data.source_id:
            try:
                frame = self.dataset_service.load_dataframe(state.data.source_id)
                state.data.schema_map = {column: str(dtype) for column, dtype in frame.dtypes.items()}
                if not state.data.column_labels:
                    state.data.column_labels = {column: column for column in frame.columns}
                if not state.data.column_aliases:
                    state.data.column_aliases = {
                        re.sub(r"[^a-zA-Z0-9]+", "_", column.strip().lower()).strip("_"): column
                        for column in frame.columns
                    }
                metrics = [
                    column
                    for column, dtype in frame.dtypes.items()
                    if pd.api.types.is_numeric_dtype(dtype)
                ]
                dimensions = [column for column in frame.columns if column not in metrics]
                state.data.columns.metrics = metrics
                state.data.columns.dimensions = dimensions
                for column in frame.columns:
                    if "date" in column.lower() or pd.api.types.is_datetime64_any_dtype(frame[column]):
                        state.data.columns.time_column = column
                        break
                return frame
            except ValueError:
                pass

        sample = [
            {"date": "2024-01-01", "region": "North", "product": "A", "sales": 120, "revenue": 1200},
            {"date": "2024-01-15", "region": "South", "product": "A", "sales": 150, "revenue": 1450},
            {"date": "2024-04-01", "region": "North", "product": "B", "sales": 180, "revenue": 1750},
            {"date": "2024-07-01", "region": "West", "product": "C", "sales": 95, "revenue": 980},
            {"date": "2024-10-01", "region": "South", "product": "B", "sales": 210, "revenue": 2150},
        ]
        frame = pd.DataFrame(sample)
        state.data.columns.metrics = ["sales", "revenue"]
        state.data.columns.dimensions = ["region", "product"]
        state.data.columns.time_column = "date"
        state.data.schema_map = {column: str(dtype) for column, dtype in frame.dtypes.items()}
        state.data.column_labels = {column: column for column in frame.columns}
        state.data.column_aliases = {
            re.sub(r"[^a-zA-Z0-9]+", "_", column.strip().lower()).strip("_"): column
            for column in frame.columns
        }
        if state.data.source_type == "unknown":
            state.data.source_type = "csv"
            state.data.source_id = state.data.source_id or "demo_sales_dataset"
        if not state.data.table_name:
            state.data.table_name = "demo_sales_dataset"
        return frame

    @staticmethod
    def _execute_sql_over_frame(
        frame: pd.DataFrame,
        state: QueryState,
        sql_override: str,
    ) -> tuple[pd.DataFrame, str]:
        table_name = state.data.table_name or "dataset"
        resolved_sql = PandasExecutor._rewrite_sql_identifiers(sql_override, state)
        connection = sqlite3.connect(":memory:")
        try:
            sql_frame = frame.copy()
            for column in sql_frame.columns:
                if "date" in column.lower():
                    sql_frame[column] = sql_frame[column].astype(str)
            sql_frame.to_sql(table_name, connection, index=False, if_exists="replace")
            return pd.read_sql_query(resolved_sql, connection), resolved_sql
        except Exception as exc:  # pragma: no cover - converted into user-facing warning upstream
            raise ValueError(str(exc)) from exc
        finally:
            connection.close()

    @staticmethod
    def _rewrite_sql_identifiers(sql: str, state: QueryState) -> str:
        rewritten = sql

        # 1. Normalize Table Name
        target_table = state.data.table_name or "dataset"
        table_patterns = [
            r'(?i)(FROM|JOIN)\s+"[^"]+"',
            r"(?i)(FROM|JOIN)\s+`[^`]+`",
            r"(?i)(FROM|JOIN)\s+([a-zA-Z0-9_]+)",
        ]
        for pattern in table_patterns:
            def _table_replacer(match):
                keyword = match.group(1)
                return f'{keyword} "{target_table}"'
            rewritten = re.sub(pattern, _table_replacer, rewritten)

        # 2. Normalize Columns
        alias_pairs = []
        for alias, canonical in state.data.column_aliases.items():
            alias_pairs.append((alias, canonical))
        for canonical, label in state.data.column_labels.items():
            alias_pairs.append((label, canonical))
        alias_pairs.sort(key=lambda item: len(str(item[0])), reverse=True)

        for source_name, canonical in alias_pairs:
            if not source_name or source_name == canonical:
                continue
            flexible = PandasExecutor._flexible_identifier_pattern(str(source_name))
            patterns = [
                rf'(?i)"{re.escape(str(source_name))}"',
                rf'(?i)`{re.escape(str(source_name))}`',
                rf'(?i)(?<!["`])\b{re.escape(str(source_name))}\b(?!["`])',
                rf'(?i)(?<!["`])\b{flexible}\b(?!["`])',
            ]
            for pattern in patterns:
                rewritten = re.sub(pattern, f'"{canonical}"', rewritten)
        rewritten = re.sub(r'"{2,}([a-zA-Z0-9_]+)"{2,}', r'"\1"', rewritten)
        return rewritten

    @staticmethod
    def _flexible_identifier_pattern(source_name: str) -> str:
        parts = [re.escape(part) for part in re.split(r"[^a-zA-Z0-9]+", source_name) if part]
        if not parts:
            return re.escape(source_name)
        return r"[\s_]*".join(parts)

    def _apply_transformations(self, frame: pd.DataFrame, state: QueryState) -> pd.DataFrame:
        data = frame.copy()
        time_column = state.data.columns.time_column

        for condition in state.transformation.filters:
            if condition.column not in data.columns:
                continue
            
            # Helper to make string comparisons case-insensitive safely
            def _normalize(series, val):
                if pd.api.types.is_string_dtype(series) and isinstance(val, str):
                    return series.astype(str).str.lower(), str(val).lower()
                return series, val
            
            series, val = _normalize(data[condition.column], condition.value)

            if condition.operator == "=":
                data = data[series == val]
            elif condition.operator == "!=":
                data = data[series != val]
            elif condition.operator == ">":
                data = data[data[condition.column] > condition.value]
            elif condition.operator == ">=":
                data = data[data[condition.column] >= condition.value]
            elif condition.operator == "<":
                data = data[data[condition.column] < condition.value]
            elif condition.operator == "<=":
                data = data[data[condition.column] <= condition.value]
            elif condition.operator == "contains":
                data = data[data[condition.column].astype(str).str.contains(str(condition.value), case=False)]

        if time_column and state.transformation.time_granularity and time_column in data.columns:
            data[time_column] = pd.to_datetime(data[time_column])
            if state.transformation.time_granularity == "monthly":
                data[time_column] = data[time_column].dt.to_period("M").astype(str)
            elif state.transformation.time_granularity == "quarterly":
                data[time_column] = data[time_column].dt.to_period("Q").astype(str)
            elif state.transformation.time_granularity == "yearly":
                data[time_column] = data[time_column].dt.year.astype(str)
            else:
                data[time_column] = data[time_column].dt.date.astype(str)

        group_by = list(state.transformation.group_by)
        if not group_by and state.transformation.time_granularity and time_column:
            group_by = [time_column]

        if group_by and state.transformation.aggregations:
            aggregate_map = {}
            for aggregation in state.transformation.aggregations:
                # Safe aggregation: default to grouping column if target doesn't exist
                target_col = aggregation.column if aggregation.column in data.columns else group_by[0]
                op = "mean" if aggregation.operation == "avg" else aggregation.operation
                aggregate_map[target_col] = op
            data = data.groupby(group_by, as_index=False).agg(aggregate_map)

        if state.transformation.sort and state.transformation.sort.column in data.columns:
            data = data.sort_values(
                by=state.transformation.sort.column,
                ascending=state.transformation.sort.order == "asc",
            )

        if state.transformation.limit:
            data = data.head(state.transformation.limit)

        return data.reset_index(drop=True)

    @staticmethod
    def _build_profile(frame: pd.DataFrame) -> dict:
        metrics = {}
        for column in frame.columns:
            if pd.api.types.is_numeric_dtype(frame[column]):
                metrics[column] = {
                    "min": float(frame[column].min()) if len(frame[column]) else 0.0,
                    "max": float(frame[column].max()) if len(frame[column]) else 0.0,
                    "mean": float(frame[column].mean()) if len(frame[column]) else 0.0,
                }
        return {
            "row_count": len(frame),
            "column_count": len(frame.columns),
            "numeric_summary": metrics,
        }
