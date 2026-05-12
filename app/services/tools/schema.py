from typing import Dict, Any
from app.services.tools.base import BaseTool, ToolResult
from app.services.data.duckdb_store import DuckDBStore

class SchemaIntrospectTool(BaseTool):
    def __init__(self, duckdb_store: DuckDBStore):
        self.duckdb = duckdb_store

    @property
    def name(self) -> str:
        return "get_schema"

    @property
    def description(self) -> str:
        return (
            "Retrieves the schema (columns and types) and a small sample of rows for a specific table. "
            "Use this at the start of a plan to understand exactly what data is available. "
            "Required argument: 'table_name' (str)."
        )

    async def execute(self, table_name: str = "", **kwargs) -> ToolResult:
        if not table_name:
            return self._error("No table_name provided.")

        if not self.duckdb.table_exists(table_name):
            return self._error(f"Table '{table_name}' does not exist in the analytical store.")

        try:
            schema = self.duckdb.get_schema(table_name)
            # Fetch a small sample (5 rows)
            sample_df = self.duckdb.execute_query(f"SELECT * FROM \"{table_name}\" LIMIT 5")
            sample_rows = sample_df.to_dict(orient="records")

            summary = (
                f"Schema for table '{table_name}': {len(schema)} columns found. "
                f"Obtained a 5-row sample for introspection."
            )

            return self._success({
                "table_name": table_name,
                "schema": schema,
                "sample_rows": sample_rows
            }, summary)

        except Exception as e:
            return self._error(f"Schema Retrieval Error: {str(e)}")
