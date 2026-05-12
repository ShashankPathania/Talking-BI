"""Session inspection endpoints."""

from fastapi import APIRouter, HTTPException

from app.api.schemas.dataset import SessionListResponse, SessionResponse, SessionSummary
from app.services.memory.session_store import SessionStore

router = APIRouter(tags=["sessions"])
store = SessionStore()


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions() -> SessionListResponse:
    sessions = await store.list_sessions()
    summaries = [
        SessionSummary(
            session_id=session.session_id,
            dataset_id=session.dataset_id,
            message_count=len(session.messages),
            query_count=len(session.query_history),
            updated_at=(
                session.query_history[-1].created_at.isoformat()
                if session.query_history
                else None
            ),
        )
        for session in sessions
    ]
    return SessionListResponse(sessions=summaries)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str) -> SessionResponse:
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(
        session_id=session.session_id,
        dataset_id=session.dataset_id,
        message_count=len(session.messages),
        messages=[
            message.model_dump(mode="json", by_alias=True) for message in session.messages
        ],
        query_state=session.query_state.model_dump(mode="json", by_alias=True),
        query_history=[
            entry.model_dump(mode="json", by_alias=True)
            for entry in session.query_history
        ],
    )
