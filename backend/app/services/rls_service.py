import logging
import re
from typing import Any

from sqlalchemy import text

from app.db.database import engine

logger = logging.getLogger(__name__)


class RLSService:
    """Row-Level Security (RLS) Service & SQL Rewriter."""

    @staticmethod
    def get_filter_for_user(user: dict[str, Any] | None, dataset_id: int) -> dict[str, str] | None:
        """Returns active RLS rule (filter_clause, description) for the user on this dataset."""
        if not user:
            return None
        # Admins bypass RLS
        if user.get("role") == "admin":
            return None

        # Check in memory if passed in user dict
        rules = user.get("rls_rules") or []
        for r in rules:
            if r.get("dataset_id") == dataset_id and r.get("filter_clause"):
                return {
                    "filter_clause": r["filter_clause"],
                    "description": r.get(
                        "description", "Dữ liệu được giới hạn theo phân quyền người dùng"
                    ),
                }

        # Otherwise query database
        user_id = user.get("id")
        if not user_id:
            return None

        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT filter_clause, description FROM public.user_dataset_rls WHERE user_id = :uid AND dataset_id = :did;"
                    ),
                    {"uid": user_id, "did": dataset_id},
                ).fetchone()
                if row and row.filter_clause:
                    return {
                        "filter_clause": row.filter_clause,
                        "description": row.description
                        or "Dữ liệu được giới hạn theo phân quyền người dùng",
                    }
        except Exception as e:
            logger.warning(f"Failed to lookup RLS filter for user {user_id}: {e}")

        return None

    @classmethod
    def rewrite_sql(cls, sql: str, filter_clause: str | None) -> str:
        """Rewrites SQL query to inject RLS filter clause safely into WHERE.

        If WHERE exists:
            ... WHERE (existing_condition) AND (filter_clause) ...
        If no WHERE:
            ... WHERE (filter_clause) [GROUP BY / ORDER BY / LIMIT ...]
        """
        if not filter_clause or not filter_clause.strip():
            return sql

        clean_sql = sql.strip().rstrip(";")
        filter_clause = filter_clause.strip()

        # Regular expressions to locate clauses
        # Find WHERE keyword (case-insensitive, as whole word not in subquery if possible)
        where_match = re.search(r"\bWHERE\b", clean_sql, re.IGNORECASE)

        if where_match:
            # Insert AND (filter_clause) after WHERE
            where_pos = where_match.end()
            # Find the rest of WHERE clause up to GROUP BY, ORDER BY, LIMIT, HAVING, or end
            tail_keywords = re.search(
                r"\b(GROUP\s+BY|ORDER\s+BY|LIMIT|HAVING|WINDOW)\b",
                clean_sql[where_pos:],
                re.IGNORECASE,
            )
            if tail_keywords:
                clause_end = where_pos + tail_keywords.start()
                existing_where = clean_sql[where_pos:clause_end].strip()
                rewritten = (
                    clean_sql[:where_pos]
                    + f" ({existing_where}) AND ({filter_clause}) "
                    + clean_sql[clause_end:]
                )
            else:
                existing_where = clean_sql[where_pos:].strip()
                rewritten = clean_sql[:where_pos] + f" ({existing_where}) AND ({filter_clause})"
        else:
            # Find where to place WHERE: before GROUP BY, ORDER BY, LIMIT, HAVING, or at the end
            clause_match = re.search(
                r"\b(GROUP\s+BY|ORDER\s+BY|LIMIT|HAVING|WINDOW)\b",
                clean_sql,
                re.IGNORECASE,
            )
            if clause_match:
                insert_pos = clause_match.start()
                rewritten = (
                    clean_sql[:insert_pos].rstrip()
                    + f" WHERE ({filter_clause}) "
                    + clean_sql[insert_pos:]
                )
            else:
                rewritten = clean_sql + f" WHERE ({filter_clause})"

        return rewritten.strip() + ";"

    @classmethod
    def get_rls_prompt_context(cls, user: dict[str, Any] | None, dataset_id: int) -> str:
        """Generate prompt guidance for Gemini explaining active RLS constraints."""
        rls_info = cls.get_filter_for_user(user, dataset_id)
        if not rls_info:
            return ""

        return (
            f"\n[QUY TẮC BẢO MẬT PHÂN QUYỀN - ROW LEVEL SECURITY]\n"
            f"- Người dùng hiện tại có phân quyền giới hạn dữ liệu: {rls_info['description']}.\n"
            f"- BẮT BUỘC câu lệnh SQL phải chứa điều kiện lọc: `{rls_info['filter_clause']}` trong mệnh đề WHERE.\n"
            f"- Trong phần giải thích, hãy nêu rõ rằng các số liệu hiển thị chỉ áp dụng trong phạm vi phân quyền này.\n"
        )
