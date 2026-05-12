from app.core.state import QueryResult, QueryState
from app.services.insight_engine import InsightEngine


def test_insight_engine_generates_trend_delta() -> None:
    engine = InsightEngine()
    state = QueryState()
    state.intent.goal = "trend_analysis"
    state.visualization.x_axis = "date"
    state.visualization.y_axis = ["revenue"]

    result = QueryResult(
        rows=[
            {"date": "2024-Q1", "revenue": 100},
            {"date": "2024-Q2", "revenue": 150},
            {"date": "2024-Q3", "revenue": 210},
        ],
        row_count=3,
        execution_mode="pandas",
        profile={"numeric_summary": {"revenue": {"min": 100.0, "max": 210.0, "mean": 153.3}}},
    )

    insights = engine.generate(state, result)
    assert any(item.title == "Trend change" for item in insights)


def test_insight_engine_generates_comparison_summary() -> None:
    engine = InsightEngine()
    state = QueryState()
    state.intent.goal = "comparison"
    state.transformation.group_by = ["region"]
    state.visualization.x_axis = "region"
    state.visualization.y_axis = ["revenue"]

    result = QueryResult(
        rows=[
            {"region": "North", "revenue": 100},
            {"region": "South", "revenue": 220},
            {"region": "West", "revenue": 130},
        ],
        row_count=3,
        execution_mode="pandas",
        profile={"numeric_summary": {"revenue": {"min": 100.0, "max": 220.0, "mean": 150.0}}},
    )

    insights = engine.generate(state, result)
    assert any(item.title == "Top comparison" and "South" in item.detail for item in insights)


def test_insight_engine_generates_anomaly_summary() -> None:
    engine = InsightEngine()
    state = QueryState()
    state.intent.goal = "trend_analysis"
    state.analysis.type = ["anomaly"]
    state.visualization.x_axis = "date"
    state.visualization.y_axis = ["revenue"]

    result = QueryResult(
        rows=[
            {"date": "2024-Q1", "revenue": 100},
            {"date": "2024-Q2", "revenue": 105},
            {"date": "2024-Q3", "revenue": 110},
            {"date": "2024-Q4", "revenue": 400},
        ],
        row_count=4,
        execution_mode="pandas",
        profile={"numeric_summary": {"revenue": {"min": 100.0, "max": 400.0, "mean": 178.75}}},
    )

    insights = engine.generate(state, result)
    assert any(item.title == "Anomaly summary" for item in insights)
    assert any(item.title.startswith("Potential anomaly #") for item in insights)


def test_insight_engine_generates_correlation_summary() -> None:
    engine = InsightEngine()
    state = QueryState()
    state.intent.goal = "correlation"
    state.visualization.x_axis = "sales"
    state.visualization.y_axis = ["revenue"]

    result = QueryResult(
        rows=[
            {"sales": 10, "revenue": 100},
            {"sales": 20, "revenue": 200},
            {"sales": 30, "revenue": 310},
            {"sales": 40, "revenue": 395},
        ],
        row_count=4,
        execution_mode="pandas",
        profile={"numeric_summary": {"sales": {"min": 10.0, "max": 40.0, "mean": 25.0}}},
    )

    insights = engine.generate(state, result)
    assert any(item.title == "Correlation summary" and "correlation" in item.detail.lower() for item in insights)


def test_insight_engine_builds_kpis_and_report_sections() -> None:
    engine = InsightEngine()
    state = QueryState()
    state.transformation.group_by = ["product_category"]
    state.visualization.y_axis = ["revenue"]
    state.data.preprocessing_profile = {
        "missing_counts": {"product_category": 0, "revenue": 2, "country": 1},
        "duplicate_rows": 3,
        "outlier_counts": {"revenue": 4, "cost": 2},
    }

    result = QueryResult(
        rows=[
            {"product_category": "Bikes", "revenue": 300},
            {"product_category": "Accessories", "revenue": 120},
            {"product_category": "Clothing", "revenue": 80},
        ],
        row_count=3,
        execution_mode="pandas",
        profile={
            "column_count": 2,
            "numeric_summary": {
                "revenue": {"min": 80.0, "max": 300.0, "mean": 166.67},
            },
        },
    )

    insights = engine.generate(state, result)
    kpis = engine.build_kpis(state, result)
    sections = engine.build_report_sections(state, result, insights)

    assert any(item.label == "Rows" for item in kpis)
    assert any(item.title == "Overview" for item in sections)
    assert any(item.title == "Data quality" for item in sections)
