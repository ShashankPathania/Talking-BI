from __future__ import annotations

import io
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.datasets import DatasetService
from app.services.execution.pandas_executor import PandasExecutor
from app.services.llm.reasoning import LLMReasoningService
from app.core.state import QueryState


def test_uploaded_file_can_execute_sql_via_virtual_table() -> None:
    dataset_root = settings.storage_root / "_tmp_sql_tests" / str(uuid4())
    dataset_root.mkdir(parents=True, exist_ok=True)
    service = DatasetService(dataset_root=dataset_root)
    executor = PandasExecutor(service)

    class SimpleUpload:
        filename = "orders.csv"

        async def read(self) -> bytes:
            return b"date,region,revenue\n2024-01-01,North,100\n2024-02-01,South,150\n"

    import asyncio

    profile = asyncio.run(service.save_upload(SimpleUpload(), dataset_name="Orders"))
    state = QueryState()
    state = service.attach_to_state(state, profile.dataset_id)

    result = executor.execute(
        state,
        sql_override='SELECT "region", SUM("revenue") AS "total_revenue" FROM "orders" GROUP BY "region" ORDER BY "total_revenue" DESC',
    )

    assert result.row_count == 2
    assert result.generated_sql is not None
    assert result.rows[0]["region"] in {"North", "South"}


def test_system_can_serve_uploaded_dataset_queries_end_to_end() -> None:
    client = TestClient(app)
    upload = client.post(
        "/v1/datasets/upload",
        files={
            "file": (
                "finance.csv",
                io.BytesIO(
                    b"date,region,revenue,sales\n2024-01-01,North,1000,120\n2024-02-01,South,1500,170\n"
                ),
            )
        },
        data={"dataset_name": "Finance"},
    )
    assert upload.status_code == 200
    dataset = upload.json()["dataset"]
    assert dataset["table_name"] == "finance"


def test_sql_validator_accepts_file_table_name() -> None:
    state = QueryState()
    state.data.source_type = "csv"
    state.data.table_name = "finance"
    assert (
        LLMReasoningService._validate_read_only_sql('SELECT * FROM "finance"', state)
        == 'SELECT * FROM "finance"'
    )
