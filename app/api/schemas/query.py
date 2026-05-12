"""Request contracts for query APIs."""

from typing import Literal

from pydantic import BaseModel, Field


class DataSourceRef(BaseModel):
    source_type: Literal["csv", "excel", "database", "unknown"] = "unknown"
    source_id: str | None = None
    table_name: str | None = None


class QueryRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None
    dataset_id: str | None = None
    data_source: DataSourceRef | None = None
