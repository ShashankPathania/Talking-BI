"""Dataset metadata models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.state import utc_now


class DatasetProfile(BaseModel):
    dataset_id: str
    name: str
    source_type: Literal["csv", "excel", "database"]
    dialect: Literal["sqlite", "postgresql", "mysql"] | None = None
    file_path: str | None = None
    table_name: str | None = None
    database_url: str | None = None
    schema_map: dict[str, str] = Field(default_factory=dict, alias="schema")
    column_labels: dict[str, str] = Field(default_factory=dict)
    column_aliases: dict[str, str] = Field(default_factory=dict)
    preprocessing_profile: dict[str, object] = Field(default_factory=dict)
    row_count: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
