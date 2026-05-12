from __future__ import annotations

import pandas as pd

from app.core.state import QueryResult, QueryState
from app.services.conversation_manager import ConversationManager
from app.services.data_preparation import DataPreparationService
from app.services.execution.pandas_executor import PandasExecutor
from app.services.visualization.plotly_builder import PlotlyBuilder


def test_data_preparation_normalizes_spreadsheet_columns() -> None:
    frame = pd.DataFrame(
        {
            "Sub Category": ["A", "B"],
            "Revenue": [100, 200],
            "Order Date": ["2024-01-01", "2024-02-01"],
        }
    )
    prepared, profile = DataPreparationService().prepare(frame)

    assert "sub_category" in prepared.columns
    assert "revenue" in prepared.columns
    assert profile["column_labels"]["sub_category"] == "Sub Category"
    assert profile["column_aliases"]["sub_category"] == "sub_category"


def test_pandas_sql_rewrite_resolves_alias_columns() -> None:
    state = QueryState()
    state.data.column_labels = {"sub_category": "Sub Category", "revenue": "Revenue"}
    state.data.column_aliases = {
        "sub_category": "sub_category",
        "subcat": "sub_category",
        "sub_category": "sub_category",
        "revenue": "revenue",
    }

    sql = 'SELECT Sub_Category, SUM(Revenue) AS total_revenue FROM finance GROUP BY "Sub Category"'
    rewritten = PandasExecutor._rewrite_sql_identifiers(sql, state)

    assert '"sub_category"' in rewritten
    assert '"revenue"' in rewritten


def test_pandas_sql_rewrite_handles_unquoted_multiword_identifier() -> None:
    state = QueryState()
    state.data.column_labels = {"sub_category": "Sub Category", "revenue": "Revenue"}
    state.data.column_aliases = {
        "sub_category": "sub_category",
        "sub_category_name": "sub_category",
        "sub_category": "sub_category",
        "subcat": "sub_category",
        "revenue": "revenue",
    }

    sql = "SELECT Sub Category, SUM(Revenue) AS sum_revenue FROM test111 GROUP BY Sub Category"
    rewritten = PandasExecutor._rewrite_sql_identifiers(sql, state)

    assert 'SELECT "sub_category", SUM("revenue")' in rewritten
    assert 'GROUP BY "sub_category"' in rewritten


def test_pandas_sql_rewrite_does_not_double_quote_existing_identifier() -> None:
    state = QueryState()
    state.data.column_labels = {"revenue": "Revenue"}
    state.data.column_aliases = {"revenue": "revenue"}

    sql = 'SELECT SUM("revenue") AS total_revenue FROM finance'
    rewritten = PandasExecutor._rewrite_sql_identifiers(sql, state)

    assert rewritten == sql


def test_dashboard_builder_returns_multiple_charts() -> None:
    rows = [
        {"order_date": "2024-01-01", "region": "North", "revenue": 100, "sales": 10},
        {"order_date": "2024-02-01", "region": "South", "revenue": 200, "sales": 20},
        {"order_date": "2024-03-01", "region": "North", "revenue": 150, "sales": 15},
    ]
    charts = PlotlyBuilder().build_dashboard(
        QueryState(),
        QueryResult(rows=rows, row_count=len(rows), execution_mode="pandas"),
    )

    assert len(charts) >= 2


def test_primary_chart_payload_uses_plain_array_points() -> None:
    rows = [
        {"state": "Alabama", "revenue": 59},
        {"state": "California", "revenue": 2807764},
    ]
    state = QueryState()
    state.visualization.chart_type = "bar"
    state.visualization.x_axis = "state"
    state.visualization.y_axis = ["revenue"]
    state.visualization.color_by = "state"

    chart = PlotlyBuilder().build(
        state,
        QueryResult(rows=rows, row_count=len(rows), execution_mode="pandas"),
        [],
    )

    assert chart is not None
    first_trace = chart.figure["data"][0]
    assert isinstance(first_trace["x"], list)
    assert isinstance(first_trace["y"], list)


def test_bar_chart_does_not_split_into_many_traces_when_color_matches_x_axis() -> None:
    rows = [
        {"state": "Alabama", "revenue": 59},
        {"state": "California", "revenue": 2807764},
    ]
    state = QueryState()
    state.visualization.chart_type = "bar"
    state.visualization.x_axis = "state"
    state.visualization.y_axis = ["revenue"]
    state.visualization.color_by = "state"

    chart = PlotlyBuilder().build(
        state,
        QueryResult(rows=rows, row_count=len(rows), execution_mode="pandas"),
        [],
    )

    assert chart is not None
    assert len(chart.figure["data"]) == 1


def test_execution_error_is_humanized_with_available_columns() -> None:
    state = QueryState()
    state.data.column_labels = {"sub_category": "Sub Category", "product": "Product"}

    text = ConversationManager._humanize_execution_error("no such column: Sub_Category", state)

    assert "Available columns include" in text
    assert "Sub Category" in text
