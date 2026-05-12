"""Unified execution interface."""

from app.core.state import ExecutionPlan, QueryResult, QueryState
from app.services.db_connectors import DatabaseConnector
from app.services.datasets import DatasetService
from app.services.execution.pandas_executor import PandasExecutor
from app.services.execution.sql_executor import SQLExecutor


class UnifiedExecutor:
    def __init__(
        self,
        dataset_service: DatasetService | None = None,
        db_connector: DatabaseConnector | None = None,
    ) -> None:
        self.db_connector = db_connector or DatabaseConnector()
        self.dataset_service = dataset_service or DatasetService(db_connector=self.db_connector)
        self.pandas_executor = PandasExecutor(self.dataset_service)
        self.sql_executor = SQLExecutor(self.db_connector)

    async def execute(
        self,
        state: QueryState,
        plan: ExecutionPlan,
        previous_result: QueryResult | None = None,
        sql_override: str | None = None,
    ) -> QueryResult:
        if plan.reuse_previous_data and previous_result is not None:
            return previous_result
        if plan.execution_mode == "sql":
            if state.data.source_id and not str(state.data.source_id).startswith("sqlite:///"):
                profile = self.dataset_service.get_profile(str(state.data.source_id))
                if profile and profile.database_url:
                    state.data.source_id = profile.database_url
                    state.data.table_name = profile.table_name
                    state.data.schema_map = profile.schema_map
            return self.sql_executor.execute(state, sql_override=sql_override)
        return self.pandas_executor.execute(state, sql_override=sql_override)
