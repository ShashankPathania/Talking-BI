from __future__ import annotations

from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app


def test_register_sqlite_database_and_query_it() -> None:
    client = TestClient(app)
    sample_frame = pd.DataFrame(
        [
            {"region": "North", "revenue": 100},
            {"region": "South", "revenue": 150},
        ]
    )

    with patch(
        "app.services.db_connectors.DatabaseConnector.inspect_table",
        return_value=type(
            "Snapshot",
            (),
            {
                "schema_map": {column: str(dtype) for column, dtype in sample_frame.dtypes.items()},
                "row_count": len(sample_frame),
            },
        )(),
    ), patch(
        "app.services.db_connectors.DatabaseConnector.execute_query",
        return_value=sample_frame,
    ):
        register = client.post(
            "/v1/datasets/register-database",
            json={
                "name": "Sales DB",
                "database_url": "sqlite:///D:/Talking_BI_v2/README.md",
                "table_name": "sales",
                "dialect": "sqlite",
            },
        )
        assert register.status_code == 200
        dataset_id = register.json()["dataset"]["dataset_id"]

        query = client.post(
            "/v1/query",
            json={
                "dataset_id": dataset_id,
                "message": "Show revenue trends by region",
            },
        )
        assert query.status_code == 200
        payload = query.json()
        assert payload["execution_plan"]["execution_mode"] == "sql"
        assert payload["query_state"]["data"]["source_type"] == "database"
        assert payload["data_preview"]
        assert payload["query_state"]["data"]["table_name"] == "sales"
