"""Semantic layer service for business glossary and verified metrics."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db.database import engine

logger = logging.getLogger(__name__)


class BusinessGlossaryItem(BaseModel):
    id: int | None = None
    dataset_id: int
    term: str = Field(..., min_length=1, max_length=255)
    target_type: str = Field(default="column", max_length=50)  # column, metric, filter
    target_name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    created_at: str | None = None


class VerifiedMetricItem(BaseModel):
    id: int | None = None
    dataset_id: int
    metric_name: str = Field(..., min_length=1, max_length=255)
    display_name: str = Field(..., min_length=1, max_length=255)
    sql_expression: str = Field(..., min_length=1)
    description: str | None = None
    created_at: str | None = None


class SemanticService:
    @staticmethod
    def get_glossary(dataset_id: int | None = None) -> list[BusinessGlossaryItem]:
        with engine.connect() as conn:
            if dataset_id is not None:
                query = text("""
                    SELECT id, dataset_id, term, target_type, target_name, description, TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS')
                    FROM public.business_glossary
                    WHERE dataset_id = :dataset_id
                    ORDER BY term ASC;
                """)
                rows = conn.execute(query, {"dataset_id": dataset_id}).fetchall()
            else:
                query = text("""
                    SELECT id, dataset_id, term, target_type, target_name, description, TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS')
                    FROM public.business_glossary
                    ORDER BY dataset_id, term ASC;
                """)
                rows = conn.execute(query).fetchall()

            return [
                BusinessGlossaryItem(
                    id=r[0],
                    dataset_id=r[1],
                    term=r[2],
                    target_type=r[3],
                    target_name=r[4],
                    description=r[5],
                    created_at=r[6],
                )
                for r in rows
            ]

    @staticmethod
    def add_glossary_term(item: BusinessGlossaryItem) -> BusinessGlossaryItem:
        with engine.begin() as conn:
            query = text("""
                INSERT INTO public.business_glossary (dataset_id, term, target_type, target_name, description)
                VALUES (:dataset_id, :term, :target_type, :target_name, :description)
                RETURNING id, TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS');
            """)
            row = conn.execute(
                query,
                {
                    "dataset_id": item.dataset_id,
                    "term": item.term.strip().lower(),
                    "target_type": item.target_type,
                    "target_name": item.target_name.strip(),
                    "description": item.description,
                },
            ).fetchone()
            if row:
                item.id = row[0]
                item.created_at = row[1]
            return item

    @staticmethod
    def delete_glossary_term(term_id: int) -> bool:
        with engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM public.business_glossary WHERE id = :id"), {"id": term_id}
            )
            return bool(result.rowcount > 0)

    @staticmethod
    def get_verified_metrics(dataset_id: int | None = None) -> list[VerifiedMetricItem]:
        with engine.connect() as conn:
            if dataset_id is not None:
                query = text("""
                    SELECT id, dataset_id, metric_name, display_name, sql_expression, description, TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS')
                    FROM public.verified_metrics
                    WHERE dataset_id = :dataset_id
                    ORDER BY display_name ASC;
                """)
                rows = conn.execute(query, {"dataset_id": dataset_id}).fetchall()
            else:
                query = text("""
                    SELECT id, dataset_id, metric_name, display_name, sql_expression, description, TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS')
                    FROM public.verified_metrics
                    ORDER BY dataset_id, display_name ASC;
                """)
                rows = conn.execute(query).fetchall()

            return [
                VerifiedMetricItem(
                    id=r[0],
                    dataset_id=r[1],
                    metric_name=r[2],
                    display_name=r[3],
                    sql_expression=r[4],
                    description=r[5],
                    created_at=r[6],
                )
                for r in rows
            ]

    @staticmethod
    def add_verified_metric(item: VerifiedMetricItem) -> VerifiedMetricItem:
        with engine.begin() as conn:
            query = text("""
                INSERT INTO public.verified_metrics (dataset_id, metric_name, display_name, sql_expression, description)
                VALUES (:dataset_id, :metric_name, :display_name, :sql_expression, :description)
                RETURNING id, TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS');
            """)
            row = conn.execute(
                query,
                {
                    "dataset_id": item.dataset_id,
                    "metric_name": item.metric_name.strip(),
                    "display_name": item.display_name.strip(),
                    "sql_expression": item.sql_expression.strip(),
                    "description": item.description,
                },
            ).fetchone()
            if row:
                item.id = row[0]
                item.created_at = row[1]
            return item

    @staticmethod
    def delete_verified_metric(metric_id: int) -> bool:
        with engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM public.verified_metrics WHERE id = :id"), {"id": metric_id}
            )
            return bool(result.rowcount > 0)

    @classmethod
    def build_semantic_context(cls, dataset_id: int | None = None) -> str:
        """Constructs an injectable Semantic Layer context string for LLM prompts."""
        if dataset_id is None:
            dataset_id = 1
        glossary = cls.get_glossary(dataset_id)
        metrics = cls.get_verified_metrics(dataset_id)

        if not glossary and not metrics:
            return ""

        lines = ["Semantic Layer & Business Glossary:"]
        if metrics:
            lines.append("Verified Golden Metrics (Data Analyst approved SQL formulas):")
            for m in metrics:
                lines.append(
                    f'- "{m.display_name}" ({m.metric_name}): {m.sql_expression}'
                    + (f" ({m.description})" if m.description else "")
                )
        if glossary:
            lines.append("Business Glossary & Synonyms (Natural language mapping):")
            for g in glossary:
                lines.append(
                    f'- "{g.term}" -> maps to {g.target_type}: {g.target_name}'
                    + (f" ({g.description})" if g.description else "")
                )

        lines.append(
            "Rule: Whenever user asks for these metrics or terms, you MUST use the mapped column names and verified formulas."
        )
        return "\n".join(lines)
