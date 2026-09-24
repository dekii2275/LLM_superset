"""Independent Streamable HTTP smoke test for the Superset MCP service."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def serialize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return serialize(value.model_dump(by_alias=True, exclude_none=True))
    if isinstance(value, dict):
        return {str(key): serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize(item) for item in value]
    return value


async def call_and_print(
    session: ClientSession, name: str, arguments: dict[str, Any] | None = None
) -> Any:
    result = await session.call_tool(name, arguments or {})
    print(f"\n{name}:")
    print(json.dumps(serialize(result), ensure_ascii=False, indent=2, default=str))
    return result


def first_text_json(result: Any) -> dict[str, Any]:
    for item in serialize(result).get("content", []):
        if item.get("type") == "text":
            try:
                return json.loads(item["text"])
            except (KeyError, TypeError, json.JSONDecodeError):
                continue
    return {}


async def main() -> None:
    url = os.getenv("SUPERSET_MCP_INTERNAL_URL", "http://superset-mcp:5008/mcp")
    print(f"Connecting to {url}")
    async with streamable_http_client(url) as streams:
        read, write, *_ = streams
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = [tool.name for tool in tools.tools]
            print("Tools:", ", ".join(tool_names))
            for tool in ("health_check", "get_instance_info"):
                if tool in tool_names:
                    await call_and_print(session, tool)
            if "search_tools" in tool_names:
                await call_and_print(session, "search_tools", {"query": "NYC Yellow Taxi dataset columns metrics"})
                await call_and_print(session, "search_tools", {"query": "NYC Yellow Taxi Overview dashboard charts"})
            if "call_tool" in tool_names:
                # Tool-search hides the full catalog; the proxy requests below
                # prove actual dataset/dashboard discovery through MCP.
                datasets_result = await call_and_print(
                    session,
                    "call_tool",
                    {"name": "list_datasets", "arguments": {"request": {}}},
                )
                datasets = first_text_json(datasets_result).get("datasets", [])
                if datasets:
                    await call_and_print(
                        session,
                        "call_tool",
                        {
                            "name": "get_dataset_info",
                            "arguments": {"request": {"identifier": datasets[0]["id"]}},
                        },
                    )
                dashboards_result = await call_and_print(
                    session,
                    "call_tool",
                    {"name": "list_dashboards", "arguments": {"request": {"search": "NYC Yellow Taxi Overview"}}},
                )
                dashboards = first_text_json(dashboards_result).get("dashboards", [])
                if dashboards:
                    await call_and_print(
                        session,
                        "call_tool",
                        {
                            "name": "get_dashboard_info",
                            "arguments": {"request": {"identifier": dashboards[0]["id"]}},
                        },
                    )


if __name__ == "__main__":
    asyncio.run(main())
