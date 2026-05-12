from __future__ import annotations

import asyncio

import numpy as np

from app.core.state import AggregationSpec, ExecutionPlan, QueryResult, QueryState
from app.services.llm.reasoning import LLMReasoningService


class FakeLLMClient:
    def __init__(self, *, json_payloads=None, text_payloads=None) -> None:
        self.json_payloads = list(json_payloads or [])
        self.text_payloads = list(text_payloads or [])

    def enabled(self) -> bool:
        return True

    async def complete_json(self, **kwargs):
        return self.json_payloads.pop(0) if self.json_payloads else None

    async def complete_text(self, **kwargs):
        return self.text_payloads.pop(0) if self.text_payloads else None


def test_llm_schema_inference_filters_unknown_columns() -> None:
    service = LLMReasoningService(
        FakeLLMClient(
            json_payloads=[
                {
                    "metrics": ["revenue", "invented_metric"],
                    "dimensions": ["region"],
                    "time_column": "date",
                }
            ]
        )
    )
    state = QueryState()
    state.data.schema_map = {
        "date": "datetime64[ns]",
        "region": "object",
        "revenue": "float64",
    }

    profile = asyncio.run(service.infer_schema(state))

    assert profile is not None
    assert profile.metrics == ["revenue"]
    assert profile.dimensions == ["region"]
    assert profile.time_column == "date"


def test_llm_primary_interpretation_sets_reasoning_metadata() -> None:
    service = LLMReasoningService(
        FakeLLMClient(
            json_payloads=[
                {
                    "intent": {"type": "analysis", "goal": "comparison", "confidence": 0.93},
                    "transformation": {
                        "filters": [],
                        "group_by": ["region"],
                        "aggregations": [{"column": "revenue", "operation": "sum"}],
                        "time_granularity": None,
                        "sort": None,
                        "limit": None,
                    },
                    "analysis": {"type": ["summary"], "parameters": {}},
                    "visualization": {
                        "chart_type": "bar",
                        "x_axis": "region",
                        "y_axis": ["revenue"],
                        "color_by": None,
                        "title": "Revenue by Region",
                        "options": {"show_legend": True, "highlight_anomalies": False},
                    },
                    "dataset_match": {
                        "matched_columns": ["region", "revenue"],
                        "missing_terms": [],
                        "notes": ["Mapped revenue and region directly."],
                    },
                    "sql": {"query": None},
                }
            ]
        )
    )
    state = QueryState()
    state.data.schema_map = {"region": "object", "revenue": "float64"}
    state.data.columns.dimensions = ["region"]
    state.data.columns.metrics = ["revenue"]

    interpreted_state, sql_block = asyncio.run(
        service.interpret_query(
            current_state=state,
            seeded_state=state,
            message="Compare revenue by region",
            chat_history=[{"role": "user", "content": "Compare revenue by region"}],
        )
    )

    assert interpreted_state is not None
    assert sql_block == {"query": None}
    assert interpreted_state.intent.goal == "comparison"
    assert interpreted_state.transformation.group_by == ["region"]
    assert interpreted_state.visualization.chart_type == "bar"
    assert interpreted_state.meta.reasoning["reasoning_mode"] == "llm_primary"
    assert interpreted_state.meta.reasoning["matched_columns"] == ["region", "revenue"]


def test_llm_plan_refinement_respects_deterministic_safety() -> None:
    service = LLMReasoningService(
        FakeLLMClient(
            json_payloads=[
                {
                    "reuse_previous_data": True,
                    "update_visualization_only": True,
                    "run_analysis": False,
                    "steps": ["reuse_previous_result", "build_chart"],
                    "rationale": "Reuse everything.",
                }
            ]
        )
    )
    deterministic_plan = ExecutionPlan(
        needs_new_fetch=True,
        reuse_previous_data=False,
        run_analysis=True,
        update_visualization_only=False,
        execution_mode="pandas",
        steps=["load_data", "transform_data", "analyze_data", "build_chart"],
        changed_sections=["data"],
        rationale="Fresh fetch required.",
    )

    current_state = QueryState()
    current_state.data.source_id = "demo"
    current_state.data.source_type = "csv"
    deterministic_plan.changed_sections = ["data"]

    refined = asyncio.run(service.refine_plan(
        previous_state=QueryState(),
        state=current_state,
        previous_result=QueryResult(rows=[{"revenue": 100}], row_count=1, execution_mode="pandas"),
        deterministic_plan=deterministic_plan,
    ))

    assert refined is not None
    assert refined.reuse_previous_data is False
    assert refined.update_visualization_only is False
    assert refined.run_analysis is False
    assert refined.rationale == "Reuse everything."


def test_llm_grounded_explanation_returns_text() -> None:
    service = LLMReasoningService(FakeLLMClient(text_payloads=["Revenue grew steadily over the returned periods."]))
    explanation = asyncio.run(service.build_grounded_explanation(
        QueryState(),
        QueryResult(rows=[{"revenue": 100}], row_count=1, execution_mode="pandas"),
        [],
        ExecutionPlan(execution_mode="pandas"),
    ))

    assert explanation == "Revenue grew steadily over the returned periods."


def test_llm_grounded_explanation_handles_numpy_scalars_in_result() -> None:
    service = LLMReasoningService(FakeLLMClient(text_payloads=["Safe explanation."]))
    explanation = asyncio.run(service.build_grounded_explanation(
        QueryState(),
        QueryResult(
            rows=[{"revenue": np.float64(100.5)}],
            row_count=1,
            execution_mode="pandas",
            profile={"numeric_summary": {"revenue": {"min": np.float64(100.5), "max": np.float64(100.5), "mean": np.float64(100.5)}}},
        ),
        [],
        ExecutionPlan(execution_mode="pandas"),
    ))

    assert explanation == "Safe explanation."


def test_llm_sql_validation_rejects_non_select_queries() -> None:
    state = QueryState()
    state.data.source_type = "database"
    state.data.table_name = "orders"
    assert LLMReasoningService._validate_read_only_sql("DELETE FROM orders", state) is None
    assert LLMReasoningService._validate_read_only_sql("SELECT * FROM orders", state) == "SELECT * FROM orders"


def test_llm_sql_is_normalized_to_canonical_columns() -> None:
    state = QueryState()
    state.data.source_type = "csv"
    state.data.table_name = "test111"
    state.data.schema_map = {
        "product_category": "object",
        "sub_category": "object",
        "revenue": "float64",
    }
    state.data.column_labels = {
        "product_category": "Product Category",
        "sub_category": "Sub Category",
        "revenue": "Revenue",
    }
    state.data.column_aliases = {
        "product_category": "product_category",
        "sub_category": "sub_category",
        "revenue": "revenue",
    }

    normalized = LLMReasoningService._normalize_sql_query(
        'SELECT `Product Category`, `Sub Category`, SUM(`Revenue`) AS `sum(Revenue)` FROM `test111` GROUP BY `Product Category`, `Sub Category`',
        state,
    )

    assert '"product_category"' in normalized
    assert '"sub_category"' in normalized
    assert '"revenue"' in normalized
    assert '""revenue""' not in normalized


def test_canonicalize_state_normalizes_interpreted_display_columns() -> None:
    service = LLMReasoningService(FakeLLMClient())
    state = QueryState()
    state.data.schema_map = {
        "product_category": "str",
        "sub_category": "str",
        "revenue": "float64",
    }
    state.data.column_labels = {
        "product_category": "Product Category",
        "sub_category": "Sub Category",
        "revenue": "Revenue",
    }
    state.data.column_aliases = {
        "product_category": "product_category",
        "sub_category": "sub_category",
        "revenue": "revenue",
    }
    state.transformation.group_by = ["Product Category", "Sub Category"]
    state.transformation.aggregations = [AggregationSpec(column="Revenue", operation="sum")]
    state.visualization.x_axis = "Product Category"
    state.visualization.color_by = "Sub Category"
    state.visualization.y_axis = ["Revenue"]
    state.meta.reasoning = {"matched_columns": ["Product Category", "Sub Category", "Revenue"]}

    normalized = service.canonicalize_state(state)

    assert normalized.transformation.group_by == ["product_category", "sub_category"]
    assert normalized.transformation.aggregations[0].column == "revenue"
    assert normalized.visualization.x_axis == "product_category"
    assert normalized.visualization.color_by == "sub_category"
    assert normalized.visualization.y_axis == ["revenue"]
