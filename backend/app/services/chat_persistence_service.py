"""Chat persistence service for sessions and messages."""

from __future__ import annotations

import json
import logging
import uuid
from numbers import Number
from typing import Any

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import text

from app.db.database import engine
from app.schemas.ai import QueryResult, VisualizationSpec
from app.services.visualization_service import VisualizationService

logger = logging.getLogger(__name__)


class ChatSession(BaseModel):
    id: str
    title: str
    dataset_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ChatMessage(BaseModel):
    id: int | None = None
    session_id: str
    sender: str  # "user" or "assistant"
    content: str
    metadata: dict[str, Any] | None = None
    created_at: str | None = None


class ChatPersistenceService:
    @staticmethod
    def _restore_legacy_cached_chart(metadata: dict[str, Any], title: str) -> dict[str, Any]:
        """Recover charts saved before cache hits included visualization metadata."""
        if not metadata.get("cached") or "visualization" in metadata or not metadata.get("query"):
            return metadata
        try:
            query = QueryResult.model_validate(metadata["query"])
            if query.error or not query.rows:
                return metadata
            planner = VisualizationService()
            spec = planner.heuristic(query)
            if spec.type == "pie" and any(
                token in title.casefold() for token in ("top", "nhiều nhất", "cao nhất")
            ):
                spec = spec.model_copy(update={"type": "bar", "title": title[:120]})
            if spec.type == "none" and len(query.rows) == 1:
                numeric = next(
                    (
                        column
                        for column in query.columns
                        if isinstance(query.rows[0].get(column), Number)
                        and not isinstance(query.rows[0].get(column), bool)
                    ),
                    None,
                )
                if numeric:
                    spec = VisualizationSpec(type="kpi", title=title or numeric, y_axis=numeric)
            if spec.type != "none":
                return {**metadata, "visualization": spec.model_dump(mode="json")}
        except Exception:
            logger.warning("Could not recover legacy cached chart", exc_info=True)
        return metadata

    @staticmethod
    def list_sessions(dataset_id: int | None = None) -> list[ChatSession]:
        with engine.connect() as conn:
            if dataset_id is not None:
                query = text("""
                    SELECT id, title, dataset_id,
                           TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS'),
                           TO_CHAR(updated_at, 'YYYY-MM-DD HH24:MI:SS')
                    FROM public.chat_sessions
                    WHERE dataset_id = :dataset_id
                    ORDER BY updated_at DESC;
                """)
                rows = conn.execute(query, {"dataset_id": dataset_id}).fetchall()
            else:
                query = text("""
                    SELECT id, title, dataset_id,
                           TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS'),
                           TO_CHAR(updated_at, 'YYYY-MM-DD HH24:MI:SS')
                    FROM public.chat_sessions
                    ORDER BY updated_at DESC;
                """)
                rows = conn.execute(query).fetchall()

            return [
                ChatSession(
                    id=r[0],
                    title=r[1],
                    dataset_id=r[2],
                    created_at=r[3],
                    updated_at=r[4],
                )
                for r in rows
            ]

    @staticmethod
    def create_session(
        title: str,
        dataset_id: int | None = None,
        session_id: str | None = None,
    ) -> ChatSession:
        sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        with engine.begin() as conn:
            query = text("""
                INSERT INTO public.chat_sessions (id, title, dataset_id)
                VALUES (:id, :title, :dataset_id)
                ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, updated_at = CURRENT_TIMESTAMP
                RETURNING id, title, dataset_id,
                          TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS'),
                          TO_CHAR(updated_at, 'YYYY-MM-DD HH24:MI:SS');
            """)
            row = conn.execute(
                query,
                {
                    "id": sid,
                    "title": title.strip() or "Hội thoại mới",
                    "dataset_id": dataset_id,
                },
            ).fetchone()
            return ChatSession(
                id=row[0],
                title=row[1],
                dataset_id=row[2],
                created_at=row[3],
                updated_at=row[4],
            )

    @staticmethod
    def get_session(session_id: str) -> ChatSession | None:
        with engine.connect() as conn:
            query = text("""
                SELECT id, title, dataset_id,
                       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS'),
                       TO_CHAR(updated_at, 'YYYY-MM-DD HH24:MI:SS')
                FROM public.chat_sessions
                WHERE id = :id;
            """)
            row = conn.execute(query, {"id": session_id}).fetchone()
            if not row:
                return None
            return ChatSession(
                id=row[0],
                title=row[1],
                dataset_id=row[2],
                created_at=row[3],
                updated_at=row[4],
            )

    @staticmethod
    def delete_session(session_id: str) -> bool:
        with engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM public.chat_sessions WHERE id = :id"),
                {"id": session_id},
            )
            return bool(result.rowcount > 0)

    @staticmethod
    def get_messages(session_id: str) -> list[ChatMessage]:
        with engine.connect() as conn:
            query = text("""
                SELECT id, session_id, sender, content, metadata_json,
                       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS')
                FROM public.chat_messages
                WHERE session_id = :session_id
                ORDER BY id ASC;
            """)
            rows = conn.execute(query, {"session_id": session_id}).fetchall()
            messages = []
            last_user_question = ""
            for r in rows:
                meta = r[4]
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = None
                if r[2] == "user":
                    last_user_question = r[3]
                elif isinstance(meta, dict):
                    meta = ChatPersistenceService._restore_legacy_cached_chart(
                        meta, last_user_question
                    )
                messages.append(
                    ChatMessage(
                        id=r[0],
                        session_id=r[1],
                        sender=r[2],
                        content=r[3],
                        metadata=meta if isinstance(meta, dict) else None,
                        created_at=r[5],
                    )
                )
            return messages

    @classmethod
    def add_message(
        cls,
        session_id: str,
        sender: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessage:
        # Ensure session exists
        session = cls.get_session(session_id)
        if not session:
            cls.create_session(title=content[:40], session_id=session_id)

        meta_json = json.dumps(jsonable_encoder(metadata), ensure_ascii=False) if metadata else None
        with engine.begin() as conn:
            query = text("""
                INSERT INTO public.chat_messages (session_id, sender, content, metadata_json)
                VALUES (:session_id, :sender, :content, CAST(:metadata_json AS jsonb))
                RETURNING id, TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS');
            """)
            row = conn.execute(
                query,
                {
                    "session_id": session_id,
                    "sender": sender,
                    "content": content,
                    "metadata_json": meta_json,
                },
            ).fetchone()

            conn.execute(
                text(
                    "UPDATE public.chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = :id"
                ),
                {"id": session_id},
            )

            return ChatMessage(
                id=row[0],
                session_id=session_id,
                sender=sender,
                content=content,
                metadata=metadata,
                created_at=row[1],
            )

    @classmethod
    def get_recent_history(cls, session_id: str, limit: int = 6) -> list[dict[str, str]]:
        messages = cls.get_messages(session_id)
        recent = messages[-limit:]
        return [{"role": m.sender, "content": m.content} for m in recent]
