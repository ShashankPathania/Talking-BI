from fastapi.testclient import TestClient
from uuid import uuid4

from app.core.state import AggregationSpec, QueryState
from app.main import app
from app.services.conversation_manager import ConversationManager


def test_session_query_history_tracks_lineage() -> None:
    client = TestClient(app)
    session_id = f"session-history-{uuid4()}"

    first = client.post(
        "/v1/query",
        json={
            "session_id": session_id,
            "message": "Show revenue trends",
            "data_source": {"source_type": "csv", "source_id": "demo"},
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/v1/query",
        json={
            "session_id": session_id,
            "message": "Make it quarterly",
        },
    )
    assert second.status_code == 200

    session = client.get(f"/v1/sessions/{session_id}")
    assert session.status_code == 200
    payload = session.json()
    assert len(payload["query_history"]) == 2
    first_entry = payload["query_history"][0]
    second_entry = payload["query_history"][1]
    assert first_entry["message"] == "Show revenue trends"
    assert second_entry["message"] == "Make it quarterly"
    assert second_entry["parent_query_id"] == first_entry["query_id"]
    assert second_entry["version"] > first_entry["version"]


def test_report_request_resets_prior_state() -> None:
    client = TestClient(app)
    session_id = f"session-report-reset-{uuid4()}"

    first = client.post(
        "/v1/query",
        json={
            "session_id": session_id,
            "message": "Show revenue by region for 2024",
            "data_source": {"source_type": "csv", "source_id": "demo"},
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/v1/query",
        json={
            "session_id": session_id,
            "message": "give me a full dataset report",
        },
    )
    assert second.status_code == 200
    payload = second.json()
    assert payload["query_state"]["transformation"]["filters"] == []
    assert payload["query_state"]["transformation"]["group_by"] == []
    assert payload["debug"]["reasoning_mode"]


def test_i_meant_followup_is_treated_as_related_correction() -> None:
    state = QueryState()
    state.meta.version = 2
    state.transformation.group_by = ["product_category"]
    state.transformation.aggregations = [AggregationSpec(column="revenue", operation="sum")]

    should_reset = ConversationManager._should_reset_state(state, "i meant sub categories like individual products not categories")
    assert should_reset is False
