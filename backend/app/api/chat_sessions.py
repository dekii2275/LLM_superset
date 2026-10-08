import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.chat_persistence_service import (
    ChatMessage,
    ChatPersistenceService,
    ChatSession,
)

router = APIRouter(prefix="/api/v1/chat/sessions", tags=["chat_sessions"])
logger = logging.getLogger(__name__)


class CreateSessionRequest(BaseModel):
    title: str = Field(default="Hội thoại mới", max_length=255)
    dataset_id: int | None = None


@router.get("", response_model=list[ChatSession])
def list_sessions(dataset_id: int | None = Query(default=None)) -> list[ChatSession]:
    """Retrieve chat sessions, optionally filtered by dataset_id."""
    try:
        return ChatPersistenceService.list_sessions(dataset_id)
    except Exception as e:
        logger.error(f"Failed to list chat sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to list chat sessions") from e


@router.post("", response_model=ChatSession)
def create_session(request: CreateSessionRequest) -> ChatSession:
    """Create a new chat session."""
    try:
        return ChatPersistenceService.create_session(
            title=request.title,
            dataset_id=request.dataset_id,
        )
    except Exception as e:
        logger.error(f"Failed to create chat session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create chat session") from e


@router.get("/{session_id}", response_model=ChatSession)
def get_session(session_id: str) -> ChatSession:
    """Get a chat session by ID."""
    session = ChatPersistenceService.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/{session_id}")
def delete_session(session_id: str) -> dict[str, bool]:
    """Delete a chat session and all its messages."""
    success = ChatPersistenceService.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True}


@router.get("/{session_id}/messages", response_model=list[ChatMessage])
def get_session_messages(session_id: str) -> list[ChatMessage]:
    """Retrieve all messages belonging to a chat session."""
    try:
        return ChatPersistenceService.get_messages(session_id)
    except Exception as e:
        logger.error(f"Failed to fetch messages for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch messages") from e
