from app.services.tools.base import BaseTool, ToolResult
from app.services.data.duckdb_store import DuckDBStore
from app.services.agent.guardrails import SQLValidator

class SQLQueryTool(BaseTool):
    def __init__(self, duckdb_store: DuckDBStore):
        self.duckdb = duckdb_store

    @property
    def name(self) -> str:
        return "run_sql_query"

    @property
    def description(self) -> str:
        return (
            "Executes a read-only SQL query against the analytical DuckDB store. "
            "Use this for calculations, trends, and filtering. "
            "Required argument: 'query' (str). "
            "Safety: strictly SELECT/WITH only. Auto-appends LIMIT 1000."
        )

    async def execute(self, query: str = "", **kwargs) -> ToolResult:
        if not query:
            return self._error("No query provided.")

        # v3.5 Safety Guard: Centralized SQL Validation
        is_valid, formatted_query, error = SQLValidator.validate_and_format(query)
        if not is_valid:
            return self._error(error or "SQL Validation failed.")

        try:
            df = self.duckdb.execute_query(formatted_query)
            
            # Format output for agent consumption
            row_count = len(df)
            if row_count == 0:
                return self._success([], "Query returned no rows.")
            
            # If result is large, we return a summary and a link to the data
            data_preview = df.head(50).to_dict(orient="records")
            summary = (
                f"Successfully executed query. Returned {row_count} rows. "
                f"Columns: {', '.join(df.columns)}. "
                f"Previewing first 50 rows."
            )
            
            # Stage 7: Numeric Profiling (Fixes "Insufficient Data" Insights)
            profile = {}
            numeric_cols = df.select_dtypes(include=["number"]).columns
            for col in numeric_cols:
                profile[col] = {
                    "min": float(df[col].min()),
                    "max": float(df[col].max()),
                    "mean": float(df[col].mean()),
                    "count": int(df[col].count())
                }
            
            # Stage 5: Logical Reflection (v3.11 Simplified)
            reflection_result_data = {
                "success": True,
                "useful": True
            }
            
            # Record Observation (Stage 5: Structured Capture)
            obs = {
                "result": {
                    "rows": data_preview,
                    "row_count": row_count,
                    "columns": list(df.columns),
                    "profile": profile
                },
                "reflection": reflection_result_data
            }

            return self._success({
                "rows": data_preview,
                "row_count": row_count,
                "columns": list(df.columns),
                "profile": profile
            }, summary)

        except Exception as e:
            return self._error(f"SQL Execution Error: {str(e)}")
