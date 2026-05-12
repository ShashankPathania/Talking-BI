from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app


POSTGRES_URL = os.getenv("TALKING_BI_TEST_POSTGRES_URL")
MYSQL_URL = os.getenv("TALKING_BI_TEST_MYSQL_URL")
TEST_TABLE = "talking_bi_test_metrics"


def _run_live_database_flow(database_url: str, dialect: str) -> None:
    client = TestClient(app)
    session_id = f"session-live-{dialect}-{uuid4()}"

    register = client.post(
        "/v1/datasets/register-database",
        json={
            "name": f"{dialect.title()} Metrics",
            "database_url": database_url,
            "table_name": TEST_TABLE,
            "dialect": dialect,
        },
    )
    assert register.status_code == 200, register.text
    dataset_id = register.json()["dataset"]["dataset_id"]

    query = client.post(
        "/v1/query",
        json={
            "session_id": session_id,
            "dataset_id": dataset_id,
            "message": "Show correlation between sales and revenue",
        },
    )
    assert query.status_code == 200, query.text
    payload = query.json()
    assert payload["execution_plan"]["execution_mode"] == "sql"
    assert payload["query_state"]["intent"]["goal"] == "correlation"
    assert payload["chart"]["chart_type"] == "scatter"
    assert any(item["title"] == "Correlation summary" for item in payload["insights"])
    assert payload["data_preview"]


@pytest.mark.skipif(not POSTGRES_URL, reason="Set TALKING_BI_TEST_POSTGRES_URL to run live PostgreSQL coverage.")
def test_live_postgresql_registration_and_query() -> None:
    _run_live_database_flow(POSTGRES_URL, "postgresql")


@pytest.mark.skipif(not MYSQL_URL, reason="Set TALKING_BI_TEST_MYSQL_URL to run live MySQL coverage.")
def test_live_mysql_registration_and_query() -> None:
    _run_live_database_flow(MYSQL_URL, "mysql")
