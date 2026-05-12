"""Dataset request and response schemas."""

from pydantic import BaseModel
from typing import Literal

from app.core.dataset import DatasetProfile


class UploadResponse(BaseModel):
    dataset: DatasetProfile


class DatasetListResponse(BaseModel):
    datasets: list[DatasetProfile]


class DatabaseRegistrationRequest(BaseModel):
    name: str
    database_url: str
    table_name: str
    dialect: Literal["sqlite", "postgresql", "mysql"] = "sqlite"


class SessionSummary(BaseModel):
    session_id: str
    dataset_id: str | None = None
    message_count: int
    query_count: int
    updated_at: str | None = None


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]


class SessionResponse(BaseModel):
    session_id: str
    dataset_id: str | None = None
    message_count: int
    messages: list[dict]
    query_state: dict
    query_history: list[dict]
