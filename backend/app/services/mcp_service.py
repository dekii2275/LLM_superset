"""Small, read-only-safe client for the local Superset MCP service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


class MCPUnavailableError(RuntimeError):
    """The MCP HTTP service could not be reached or initialized."""


class MCPToolError(RuntimeError):
    """An MCP tool call was invalid, blocked, or failed."""


_WRITE_TERMS = frozenset(
    {
        "create",
        "update",
        "delete",
        "write",
        "save",
        "execute",
        "sql",
        "query",
        "mutation",
        "import",
        "upload",
    }
)
_SAFE_META_TOOLS = frozenset(
    {"health_check", "get_instance_info", "search_tools", "call_tool"}
)
# These are the read-only Superset 6.1 tools the proxy may invoke in this
# phase. A positive allowlist is intentional: keyword matching alone would
# miss write operations such as add_chart_to_existing_dashboard.
_SAFE_DISCOVERY_TARGETS = frozenset(
    {
        "health_check",
        "get_instance_info",
        "get_dataset_info",
        "list_datasets",
        "get_dashboard_info",
        "list_dashboards",
        "get_chart_info",
        "list_charts",
        "get_database_info",
        "list_databases",
        "get_schema",
    }
)
_REQUEST_WRAPPED_TARGETS = frozenset(
    {
        "get_dataset_info",
        "list_datasets",
        "get_dashboard_info",
        "list_dashboards",
        "get_chart_info",
        "list_charts",
        "get_database_info",
        "list_databases",
        "get_schema",
        "generate_chart",
        "generate_explore_link",
        "update_chart",
    }
)


def jsonable(value: Any) -> Any:
    """Turn SDK/Pydantic objects into JSON-compatible data without secrets."""
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump(by_alias=True, exclude_none=True))
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


class SupersetMCPService:
    def __init__(self, url: str, *, allow_write: bool = False) -> None:
        self.url = url
        self.allow_write = allow_write

    @asynccontextmanager
    async def session(self) -> AsyncIterator[ClientSession]:
        try:
            async with streamable_http_client(self.url) as streams:
                read, write, *_ = streams
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    yield client
        except MCPToolError:
            raise
        except Exception as error:
            raise MCPUnavailableError("Superset MCP is unavailable") from error

    async def list_tools(self) -> list[dict[str, Any]]:
        async with self.session() as client:
            response = await client.list_tools()
            return [jsonable(tool) for tool in response.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        arguments = self._normalize_proxy_arguments(name, arguments)
        self._ensure_allowed(name, arguments)
        async with self.session() as client:
            response = await client.call_tool(name, arguments)
        # Evaluate an MCP response after the streamable-HTTP session closes.
        # Raising inside the SDK task group wraps the error in ExceptionGroup
        # and incorrectly makes a tool validation error look like an outage.
        result = jsonable(response)
        if result.get("isError"):
            raise MCPToolError(f"Superset MCP tool '{name}' reported an error")
        for item in result.get("content", []):
            if item.get("type") == "text" and str(item.get("text", "")).startswith("Error:"):
                raise MCPToolError(f"Superset MCP tool '{name}' reported an error")
        return result

    async def search_tools(self, query: str) -> dict[str, Any]:
        return await self.call_tool("search_tools", {"query": query})

    async def get_dataset_info(self, query: str) -> dict[str, Any]:
        """Discover dataset-related tools through Superset's tool-search proxy."""
        return await self.search_tools(f"dataset metadata columns metrics: {query}")

    def _ensure_allowed(self, name: str, arguments: dict[str, Any]) -> None:
        normalized_name = name.lower()
        if name not in _SAFE_META_TOOLS and self._looks_write_capable(normalized_name):
            raise MCPToolError(f"MCP tool '{name}' is disabled by the read-only policy")
        if name == "call_tool":
            target = str(arguments.get("name", "")).lower()
            if not target:
                raise MCPToolError("call_tool requires a target tool name")
            if not self.allow_write and target not in _SAFE_DISCOVERY_TARGETS:
                raise MCPToolError(f"MCP tool '{target}' is disabled by the read-only policy")
        elif not self.allow_write and name not in _SAFE_META_TOOLS | _SAFE_DISCOVERY_TARGETS:
            raise MCPToolError(f"MCP tool '{name}' is disabled by the read-only policy")

    @staticmethod
    def _normalize_proxy_arguments(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Accept compact Gemini arguments and adapt them to Superset's request models."""
        if name != "call_tool":
            return arguments
        target = str(arguments.get("name", ""))
        nested = arguments.get("arguments")
        if target in _REQUEST_WRAPPED_TARGETS and isinstance(nested, dict):
            request = dict(nested.get("request", nested))
            # Superset 6.1 identifies an existing dataset/dashboard by the
            # generic `identifier` field. Models commonly infer resource-
            # specific aliases from tool names, so normalize those aliases at
            # the trusted local boundary rather than sending invalid calls.
            identifier_aliases = {
                "get_dataset_info": "dataset_id",
                "get_dashboard_info": "dashboard_id",
                "get_chart_info": "chart_id",
                "get_database_info": "database_id",
                "update_chart": "chart_id",
            }
            if target in identifier_aliases and "identifier" not in request:
                alias = identifier_aliases[target]
                if alias in request:
                    request["identifier"] = request.pop(alias)
                elif "id" in request:
                    request["identifier"] = request.pop("id")
            if target == "get_schema" and "model_type" not in request:
                if "model_name" in request:
                    request["model_type"] = request.pop("model_name")
            # Gemini often infers `chart_config` from the tool description,
            # while Superset's request model requires the field to be `config`.
            # The chart type belongs inside config; a top-level value is ignored.
            if target in {"generate_chart", "generate_explore_link", "update_chart"}:
                if "config" not in request and isinstance(request.get("chart_config"), dict):
                    request["config"] = request.pop("chart_config")
                if (
                    isinstance(request.get("config"), dict)
                    and "chart_type" in request
                    and "chart_type" not in request["config"]
                ):
                    request["config"]["chart_type"] = request["chart_type"]
            return {**arguments, "arguments": {"request": request}}
        return arguments

    @staticmethod
    def _looks_write_capable(name: str) -> bool:
        return any(term in name for term in _WRITE_TERMS)
