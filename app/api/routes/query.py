"""Conversational BI query endpoint."""

from fastapi import APIRouter

from app.api.schemas.query import QueryRequest
from app.api.schemas.response import QueryResponse
from app.services.conversation_manager import ConversationManager

router = APIRouter(tags=["query"])
manager = ConversationManager()


@router.post("/query", response_model=QueryResponse)
async def run_query(request: QueryRequest) -> QueryResponse:
    return await manager.handle_query(request)
