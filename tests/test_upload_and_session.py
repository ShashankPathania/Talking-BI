from __future__ import annotations

import io
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_upload_dataset_then_query_and_fetch_session() -> None:
    client = TestClient(app)
    session_id = f"session-upload-{uuid4()}"

    upload = client.post(
        "/v1/datasets/upload",
        files={"file": ("sales.csv", io.BytesIO(b"date,region,revenue\n2024-01-01,North,100\n2024-04-01,South,150\n"))},
        data={"dataset_name": "Quarterly Revenue"},
    )
    assert upload.status_code == 200
    dataset_id = upload.json()["dataset"]["dataset_id"]

    query = client.post(
        "/v1/query",
        json={
            "session_id": session_id,
            "dataset_id": dataset_id,
            "message": "Show revenue trends by region",
        },
    )
    assert query.status_code == 200
    query_payload = query.json()
    assert query_payload["session_id"] == session_id
    assert query_payload["query_state"]["data"]["source_id"] == dataset_id
    assert query_payload["data_preview"]

    session = client.get(f"/v1/sessions/{session_id}")
    assert session.status_code == 200
    session_payload = session.json()
    assert session_payload["dataset_id"] == dataset_id
    assert session_payload["message_count"] >= 2
    assert len(session_payload["messages"]) >= 2
    assert len(session_payload["query_history"]) == 1
    assert session_payload["query_history"][0]["version"] >= 2
    assert session_payload["query_history"][0]["message"] == "Show revenue trends by region"

    sessions = client.get("/v1/sessions")
    assert sessions.status_code == 200
    assert any(item["session_id"] == session_id for item in sessions.json()["sessions"])


def test_uploaded_dataset_query_can_be_cached_without_serialization_failure() -> None:
    client = TestClient(app)
    session_id = f"session-cache-upload-{uuid4()}"

    upload = client.post(
        "/v1/datasets/upload",
        files={
            "file": (
                "metrics.csv",
                io.BytesIO(
                    b"date,region,revenue,sales\n2024-01-01,North,1000.5,120\n2024-02-01,South,1400.25,150\n"
                ),
            )
        },
        data={"dataset_name": "Metrics Cache Regression"},
    )
    assert upload.status_code == 200
    dataset_id = upload.json()["dataset"]["dataset_id"]

    first = client.post(
        "/v1/query",
        json={
            "session_id": session_id,
            "dataset_id": dataset_id,
            "message": "Show revenue trends",
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/v1/query",
        json={
            "session_id": session_id,
            "dataset_id": dataset_id,
            "message": "Show revenue trends",
        },
    )
    assert second.status_code == 200
    assert second.json()["query_state"]["meta"]["is_cached"] is True

    session = client.get(f"/v1/sessions/{session_id}")
    assert session.status_code == 200
    assert session.json()["dataset_id"] == dataset_id
