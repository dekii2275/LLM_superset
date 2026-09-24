"""Small read-only PostgreSQL query service for the NL2SQL demo."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Iterator

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import engine as default_engine
from app.schemas.ai import QueryResult


class SQLValidationError(ValueError):
    """Raised when a generated query violates the demo's read-only policy."""


_FORBIDDEN_KEYWORDS = frozenset(
    {
        "alter",
        "analyze",
        "begin",
        "call",
        "checkpoint",
        "cluster",
        "comment",
        "commit",
        "copy",
        "create",
        "deallocate",
        "delete",
        "discard",
        "do",
        "drop",
        "execute",
        "grant",
        "insert",
        "into",
        "load",
        "lock",
        "merge",
        "notify",
        "prepare",
        "reindex",
        "refresh",
        "release",
        "reset",
        "revoke",
        "rollback",
        "savepoint",
        "security",
        "set",
        "show",
        "start",
        "transaction",
        "truncate",
        "unlisten",
        "update",
        "vacuum",
    }
)


@dataclass(frozen=True)
class _Token:
    value: str
    start: int
    end: int
    depth: int


def _tokens(sql: str) -> Iterator[_Token]:
    """Yield lexical tokens while ignoring quoted literals and SQL comments.

    This is deliberately a lightweight guardrail, not a SQL parser. Keeping it
    separate makes replacing it with sqlglot later a local change.
    """

    index = 0
    depth = 0
    length = len(sql)
    while index < length:
        char = sql[index]
        if char.isspace():
            index += 1
            continue
        if sql.startswith("--", index):
            newline = sql.find("\n", index + 2)
            index = length if newline == -1 else newline + 1
            continue
        if sql.startswith("/*", index):
            end_comment = sql.find("*/", index + 2)
            if end_comment == -1:
                raise SQLValidationError("SQL contains an unclosed comment")
            index = end_comment + 2
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            while index < length:
                if sql[index] == quote:
                    if quote == "'" and index + 1 < length and sql[index + 1] == quote:
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            else:
                raise SQLValidationError("SQL contains an unclosed quoted value")
            continue
        if char == "$":
            match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[index:])
            if match:
                delimiter = match.group(0)
                close_at = sql.find(delimiter, index + len(delimiter))
                if close_at == -1:
                    raise SQLValidationError("SQL contains an unclosed dollar-quoted value")
                index = close_at + len(delimiter)
                continue
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")":
            depth -= 1
            if depth < 0:
                raise SQLValidationError("SQL contains unbalanced parentheses")
            index += 1
            continue
        if char == ";":
            yield _Token(";", index, index + 1, depth)
            index += 1
            continue
        if char.isalnum() or char == "_":
            start = index
            index += 1
            while index < length and (sql[index].isalnum() or sql[index] in {"_", "$"}):
                index += 1
            yield _Token(sql[start:index].lower(), start, index, depth)
            continue
        index += 1
    if depth != 0:
        raise SQLValidationError("SQL contains unbalanced parentheses")


class QueryService:
    def __init__(
        self,
        engine: Engine = default_engine,
        *,
        default_limit: int = 100,
        max_limit: int = 500,
        timeout_seconds: int = 10,
    ) -> None:
        self.engine = engine
        self.default_limit = max(1, min(default_limit, max_limit))
        self.max_limit = max(1, max_limit)
        self.timeout_ms = max(1, timeout_seconds) * 1_000

    def prepare_sql(self, sql: str) -> str:
        """Validate a single read-only statement and enforce a bounded result."""
        if not sql or not sql.strip():
            raise SQLValidationError("SQL is empty")

        scanned = list(_tokens(sql))
        if not scanned:
            raise SQLValidationError("SQL is empty")
        semicolons = [token for token in scanned if token.value == ";"]
        if len(semicolons) > 1 or (semicolons and scanned[-1] != semicolons[0]):
            raise SQLValidationError("Only one SQL statement is allowed")
        if semicolons:
            sql = sql[: semicolons[0].start].rstrip()
            scanned = [token for token in scanned if token.value != ";"]

        if not scanned:
            raise SQLValidationError("SQL is empty")
        if scanned[0].value not in {"select", "with"}:
            raise SQLValidationError("Only SELECT or WITH ... SELECT queries are allowed")
        if scanned[0].value == "with" and not any(
            token.value == "select" and token.depth == 0 for token in scanned
        ):
            raise SQLValidationError("WITH queries must end in a top-level SELECT")
        dangerous = next((token.value for token in scanned if token.value in _FORBIDDEN_KEYWORDS), None)
        if dangerous:
            raise SQLValidationError(f"Read-only policy blocked keyword: {dangerous.upper()}")

        top_level = [token for token in scanned if token.depth == 0]
        limit_index = next((index for index, token in enumerate(top_level) if token.value == "limit"), None)
        if limit_index is not None:
            next_token = top_level[limit_index + 1] if limit_index + 1 < len(top_level) else None
            if next_token and (next_token.value == "all" or next_token.value.isdigit()):
                requested = self.max_limit if next_token.value == "all" else int(next_token.value)
                if requested > self.max_limit:
                    sql = f"{sql[:next_token.start]}{self.max_limit}{sql[next_token.end:]}"
            return sql
        if any(token.value == "fetch" for token in top_level):
            return sql

        offset = next((token for token in top_level if token.value == "offset"), None)
        if offset:
            return f"{sql[:offset.start].rstrip()}\nLIMIT {self.default_limit}\n{sql[offset.start:]}"
        return f"{sql.rstrip()}\nLIMIT {self.default_limit}"

    async def execute_query(self, sql: str) -> QueryResult:
        """Execute validated SQL in a read-only transaction without blocking FastAPI."""
        prepared_sql = self.prepare_sql(sql)
        return await asyncio.to_thread(self._execute_sync, prepared_sql)

    def _execute_sync(self, sql: str) -> QueryResult:
        started = time.monotonic()
        try:
            with self.engine.connect() as connection:
                # This database-level backstop remains effective even if the
                # lightweight validator is later bypassed or replaced.
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text(f"SET LOCAL statement_timeout = {self.timeout_ms}"))
                result = connection.execute(text(sql))
                columns = list(result.keys())
                rows = [dict(row._mapping) for row in result]
                connection.rollback()
            return QueryResult(
                sql=sql,
                columns=columns,
                rows=rows,
                row_count=len(rows),
                execution_time_ms=round((time.monotonic() - started) * 1_000),
            )
        except SQLAlchemyError as error:
            message = str(getattr(error, "orig", error))
            if "statement timeout" in message.lower() or "query_canceled" in message.lower():
                message = "Query timed out"
            return QueryResult(
                sql=sql,
                execution_time_ms=round((time.monotonic() - started) * 1_000),
                error=message[:1_000],
            )
