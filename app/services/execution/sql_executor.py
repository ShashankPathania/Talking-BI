"""SQL execution path placeholder with deterministic SQL generation."""

from __future__ import annotations

from typing import Any

from app.core.state import QueryResult, QueryState
from app.services.db_connectors import DatabaseConnector


class SQLExecutor:
    def __init__(self, db_connector: DatabaseConnector | None = None) -> None:
        self.db_connector = db_connector or DatabaseConnector()

    def execute(self, state: QueryState, sql_override: str | None = None) -> QueryResult:
        generated_sql = sql_override or self._build_sql(state)
        rows, schema = self._execute_sql(state, generated_sql)
        return QueryResult(
            rows=rows,
            row_count=len(rows),
            schema=schema,
            execution_mode="sql",
            generated_sql=generated_sql,
            executed_sql=generated_sql,
            profile=self._build_profile(rows, schema),
        )

    def _build_sql(self, state: QueryState) -> str:
        table_name = state.data.table_name or "dataset"
        group_by = list(state.transformation.group_by)
        aggregations = state.transformation.aggregations

        select_parts: list[str] = []
        if group_by:
            select_parts.extend([f'"{column}"' for column in group_by])
        if aggregations:
            for aggregation in aggregations:
                function = "AVG" if aggregation.operation == "avg" else aggregation.operation.upper()
                alias = f'{aggregation.operation}_{aggregation.column}'
                select_parts.append(f'{function}("{aggregation.column}") AS "{alias}"')
        if not select_parts:
            select_parts.append("*")

        sql = f'SELECT {", ".join(select_parts)} FROM "{table_name}"'
        where_clause = self._build_where_clause(state)
        if where_clause:
            sql += f" WHERE {where_clause}"
        if group_by and aggregations:
            group_by_clause = ", ".join(f'"{column}"' for column in group_by)
            sql += f" GROUP BY {group_by_clause}"

        sort_column = self._resolve_sort_column(state)
        if sort_column:
            direction = state.transformation.sort.order.upper() if state.transformation.sort else "ASC"
            sql += f' ORDER BY "{sort_column}" {direction}'
        limit = state.transformation.limit or 100
        sql += f" LIMIT {limit}"
        return sql

    @staticmethod
    def _build_where_clause(state: QueryState) -> str:
        clauses: list[str] = []
        for condition in state.transformation.filters:
            value = condition.value
            if isinstance(value, str):
                safe_value = value.replace("'", "''")
                if condition.operator == "contains":
                    clauses.append(f'"{condition.column}" LIKE \'%{safe_value}%\'')
                else:
                    clauses.append(f'"{condition.column}" {condition.operator} \'{safe_value}\'')
            else:
                clauses.append(f'"{condition.column}" {condition.operator} {value}')
        return " AND ".join(clauses)

    @staticmethod
    def _resolve_sort_column(state: QueryState) -> str | None:
        if state.transformation.sort:
            return state.transformation.sort.column
        if state.transformation.aggregations:
            first = state.transformation.aggregations[0]
            return f"{first.operation}_{first.column}"
        if state.transformation.group_by:
            return state.transformation.group_by[0]
        return None

    def _execute_sql(self, state: QueryState, sql: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
        database_url = state.data.source_id
        if state.data.source_type != "database" or not database_url:
            return [], state.data.schema_map

        dialect = self._infer_dialect(str(database_url))
        if dialect is None:
            return [], state.data.schema_map

        frame = self.db_connector.execute_query(dialect, str(database_url), sql)
        return frame.to_dict(orient="records"), {column: str(dtype) for column, dtype in frame.dtypes.items()}

    @staticmethod
    def _build_profile(rows: list[dict[str, Any]], schema: dict[str, str]) -> dict[str, Any]:
        numeric_columns = [
            column
            for column, dtype in schema.items()
            if any(token in dtype.lower() for token in ["int", "float", "double", "decimal"])
        ]
        summary: dict[str, dict[str, float]] = {}
        for column in numeric_columns:
            values = [float(row[column]) for row in rows if row.get(column) is not None]
            if not values:
                continue
            summary[column] = {
                "min": min(values),
                "max": max(values),
                "mean": sum(values) / len(values),
            }
        return {
            "row_count": len(rows),
            "column_count": len(schema),
            "numeric_summary": summary,
        }

    @staticmethod
    def _infer_dialect(database_url: str) -> str | None:
        if database_url.startswith("sqlite:///"):
            return "sqlite"
        if database_url.startswith("postgresql://") or database_url.startswith("postgresql+psycopg://"):
            return "postgresql"
        if database_url.startswith("mysql://") or database_url.startswith("mysql+pymysql://"):
            return "mysql"
        return None
