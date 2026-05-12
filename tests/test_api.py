from fastapi.testclient import TestClient
import sqlite3
from pathlib import Path
from uuid import uuid4

from app.main import app


def test_frontend_root_serves_browser_ui() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Talking BI MVP" in response.text


def test_query_endpoint_returns_stateful_response() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/query",
        json={
            "message": "Show revenue trends by region",
            "data_source": {"source_type": "csv", "source_id": "demo"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"]
    assert payload["query_state"]["intent"]["goal"] == "trend_analysis"
    assert payload["query_state"]["visualization"]["chart_type"] in {"line", "bar"}
    assert payload["chart"]["chart_type"] in {"line", "bar"}
    assert "debug" in payload
    assert "reasoning_mode" in payload["debug"]


def test_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dataset_list_endpoint_returns_collection() -> None:
    client = TestClient(app)
    response = client.get("/v1/datasets")
    assert response.status_code == 200
    assert "datasets" in response.json()


def test_system_status_endpoint_reports_runtime_flags() -> None:
    client = TestClient(app)
    response = client.get("/v1/system/status")
    assert response.status_code == 200
    payload = response.json()
    assert "llm_enabled" in payload
    assert "groq_configured" in payload


def test_multi_turn_chart_switch_reuses_previous_result() -> None:
    client = TestClient(app)
    session_id = f"session-chart-switch-{uuid4()}"

    first = client.post(
        "/v1/query",
        json={
            "session_id": session_id,
            "message": "Show revenue trends by region",
            "data_source": {"source_type": "csv", "source_id": "demo"},
        },
    )
    assert first.status_code == 200
    assert first.json()["chart"]["chart_type"] in {"line", "bar"}

    second = client.post(
        "/v1/query",
        json={
            "session_id": session_id,
            "message": "Switch to bar chart",
        },
    )
    assert second.status_code == 200
    payload = second.json()
    assert payload["chart"]["chart_type"] == "bar"
    assert payload["execution_plan"]["update_visualization_only"] is True
    assert payload["execution_plan"]["reuse_previous_data"] is True


def test_query_response_includes_metric_profile_insight() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/query",
        json={
            "message": "Show revenue trends",
            "data_source": {"source_type": "csv", "source_id": "demo"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert any(
        "average" in insight["detail"].lower() or "range" in insight["title"].lower()
        for insight in payload["insights"]
    )


def test_identical_query_hits_result_cache() -> None:
    client = TestClient(app)

    first = client.post(
        "/v1/query",
        json={
            "message": "Show revenue trends by region",
            "data_source": {"source_type": "csv", "source_id": "demo"},
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/v1/query",
        json={
            "message": "Show revenue trends by region",
            "data_source": {"source_type": "csv", "source_id": "demo"},
        },
    )
    assert second.status_code == 200
    payload = second.json()
    assert payload["query_state"]["meta"]["is_cached"] is True
    assert payload["execution_plan"]["reuse_previous_data"] is True
    assert payload["execution_plan"]["steps"][0] == "reuse_cached_result"


def test_correlation_query_returns_scatter_and_correlation_insight() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/query",
        json={
            "message": "Show correlation between sales and revenue",
            "data_source": {"source_type": "csv", "source_id": "demo"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["query_state"]["intent"]["goal"] == "correlation"
    assert payload["chart"]["chart_type"] == "scatter"
    assert any(item["title"] == "Correlation summary" for item in payload["insights"])


def test_dataset_report_response_includes_kpis_sections_and_multiple_charts() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/query",
        json={
            "message": "Give me a full dataset report",
            "data_source": {"source_type": "csv", "source_id": "demo"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["kpis"]
    assert payload["report_sections"]
    assert len(payload["charts"]) >= 2


def test_conversational_prompt_returns_guidance_instead_of_breaking() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/query",
        json={
            "message": "hello",
            "data_source": {"source_type": "csv", "source_id": "demo"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "ready to analyze" in payload["explanation"].lower()
    assert payload["execution_plan"]["execution_mode"] in {"none", "pandas"}
    assert payload["chart"] is None


def test_register_database_endpoint_accepts_sqlite_source(tmp_path: Path) -> None:
    db_path = tmp_path / "sales.sqlite"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE sales_data (region TEXT, revenue REAL)")
        connection.execute("INSERT INTO sales_data (region, revenue) VALUES ('North', 100.0), ('South', 150.0)")
        connection.commit()
    finally:
        connection.close()

    client = TestClient(app)
    response = client.post(
        "/v1/datasets/register-database",
        json={
            "name": "SQLite Sales",
            "database_url": f"sqlite:///{db_path}",
            "table_name": "sales_data",
            "dialect": "sqlite",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset"]["source_type"] == "database"
    assert payload["dataset"]["table_name"] == "sales_data"
