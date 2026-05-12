"""Canonical query-state models for Talking BI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IntentLayer(BaseModel):
    type: str = "analysis"
    goal: str = "summary"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ColumnProfile(BaseModel):
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    time_column: str | None = None


class DataLayer(BaseModel):
    source_type: str = "unknown"  # Relaxed from Literal to handle LLM variance
    source_id: str | None = None
    active_dataset_id: str | None = None  # Context binding for v3.5 agent
    table_name: str | None = None
    available_tables: list[str] = Field(default_factory=list)  # Discovered tables
    columns: ColumnProfile = Field(default_factory=ColumnProfile)
    schema_map: dict[str, str] = Field(default_factory=dict, alias="schema")
    column_labels: dict[str, str] = Field(default_factory=dict)
    column_aliases: dict[str, str] = Field(default_factory=dict)
    preprocessing_profile: dict[str, Any] = Field(default_factory=dict)


class FilterCondition(BaseModel):
    column: str
    operator: Literal["=", "!=", ">", ">=", "<", "<=", "in", "contains"]
    value: Any


class AggregationSpec(BaseModel):
    column: str
    operation: Literal["sum", "avg", "count", "min", "max"] = "sum"


class SortSpec(BaseModel):
    column: str
    order: Literal["asc", "desc"] = "asc"


class TransformationLayer(BaseModel):
    filters: list[FilterCondition] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    aggregations: list[AggregationSpec] = Field(default_factory=list)

    @field_validator("group_by", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v]
        return v
    time_granularity: Literal["daily", "monthly", "quarterly", "yearly"] | None = None
    sort: SortSpec | None = None
    limit: int | None = None


class AnalysisParameters(BaseModel):
    anomaly_detection: dict[str, Any] = Field(
        default_factory=lambda: {"method": "z_score", "threshold": 2.5}
    )


class AnalysisLayer(BaseModel):
    type: list[str] = Field(
        default_factory=list
    )
    parameters: AnalysisParameters = Field(default_factory=AnalysisParameters)

    @field_validator("type", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v]
        return v


class VisualizationOptions(BaseModel):
    highlight_anomalies: bool = False
    show_legend: bool = True


class VisualizationLayer(BaseModel):
    chart_type: Literal["line", "bar", "scatter", "histogram", "table", "pie"] = "table"
    x_axis: str | None = None
    y_axis: list[str] = Field(default_factory=list)
    color_by: str | None = None
    title: str = "Analysis"
    options: VisualizationOptions = Field(default_factory=VisualizationOptions)

    @field_validator("y_axis", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v]
        return v


class MetaLayer(BaseModel):
    query_id: str = Field(default_factory=lambda: str(uuid4()))
    parent_query_id: str | None = None
    version: int = 1
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    is_cached: bool = False
    reasoning: dict[str, Any] = Field(default_factory=dict)
    
    # Stage 1: v4.0 Dashboard & Satisfaction Tracking
    charts: list[Any] = Field(default_factory=list) # ChartPayloads
    generated_views: list[str] = Field(default_factory=list) # Prevent redundancy
    coverage: dict[str, bool] = Field(default_factory=lambda: {
        "kpi": False, "distribution": False, "trend": False, "top_n": False
    })
    satisfaction: dict[str, bool] = Field(default_factory=lambda: {
        "has_visualization": False, "explicit_goal_met": False
    })
    
    # Internal Loop State
    schema_done: bool = False
    last_tool: str | None = None
    no_progress_steps: int = 0
    harvested_args: dict[str, Any] = Field(default_factory=dict) # v4.2 Recovery
    last_sql_result: dict[str, Any] | None = None # v4.3 Analytical Memory


class QueryState(BaseModel):
    intent: IntentLayer = Field(default_factory=IntentLayer)
    data: DataLayer = Field(default_factory=DataLayer)
    transformation: TransformationLayer = Field(default_factory=TransformationLayer)
    analysis: AnalysisLayer = Field(default_factory=AnalysisLayer)
    visualization: VisualizationLayer = Field(default_factory=VisualizationLayer)
    meta: MetaLayer = Field(default_factory=MetaLayer)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime = Field(default_factory=utc_now)


class QueryResult(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    schema_map: dict[str, str] = Field(default_factory=dict, alias="schema")
    execution_mode: Literal["pandas", "sql", "none"] = "none"
    generated_sql: str | None = None
    executed_sql: str | None = None
    profile: dict[str, Any] = Field(default_factory=dict)


class InsightItem(BaseModel):
    title: str
    detail: str
    confidence: Literal["high", "medium", "low"] = "medium"


class KpiCard(BaseModel):
    label: str
    value: str
    context: str | None = None


class ReportSection(BaseModel):
    title: str
    summary: str
    bullets: list[str] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    needs_new_fetch: bool = True
    reuse_previous_data: bool = False
    run_analysis: bool = True
    update_visualization_only: bool = False
    execution_mode: Literal["pandas", "sql", "none"] = "none"
    steps: list[str] = Field(default_factory=list)
    changed_sections: list[str] = Field(default_factory=list)
    rationale: str = ""


class QueryHistoryEntry(BaseModel):
    query_id: str
    parent_query_id: str | None = None
    version: int
    message: str
    query_state: QueryState
    execution_mode: str
    row_count: int
    cached: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class SessionState(BaseModel):
    session_id: str
    dataset_id: str | None = None
    query_state: QueryState = Field(default_factory=QueryState)
    messages: list[ChatMessage] = Field(default_factory=list)
    last_result: QueryResult | None = None
    query_history: list[QueryHistoryEntry] = Field(default_factory=list)


class ChartPayload(BaseModel):
    figure: dict[str, Any]
    chart_type: str
    title: str | None = None


class DebugPayload(BaseModel):
    reasoning_mode: str = "unknown"
    matched_columns: list[str] = Field(default_factory=list)
    missing_terms: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    sql_mode: str | None = None
    generated_sql: str | None = None
    executed_sql: str | None = None


class AgentReflection(BaseModel):
    success: bool
    useful: bool
    error_detected: bool = False
    next_action: str = "continue"  # Relaxed from Literal["continue", "retry", "finish"]
    reason: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class BIResponse(BaseModel):
    session_id: str
    explanation: str
    insights: list[InsightItem] = Field(default_factory=list)
    kpis: list[KpiCard] = Field(default_factory=list)
    report_sections: list[ReportSection] = Field(default_factory=list)
    chart: ChartPayload | None = None
    charts: list[ChartPayload] = Field(default_factory=list)
    query_state: QueryState
    data_preview: list[dict[str, Any]] = Field(default_factory=list)
    execution_plan: ExecutionPlan
    debug: DebugPayload = Field(default_factory=DebugPayload)
    warnings: list[str] = Field(default_factory=list)
    agent_steps: list[dict[str, Any]] = Field(default_factory=list)  # v3.5 UI progress
