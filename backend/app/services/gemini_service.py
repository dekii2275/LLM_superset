"""Gemini adapter; it receives MCP function definitions but no database secrets."""

from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

from app.schemas.ai import (
    ChartPlan,
    DashboardPlan,
    EditChartPlan,
    EditDashboardPlan,
    IntentResult,
    QueryResult,
    SQLGenerationResult,
    VisualizationSpec,
)


SYSTEM_INSTRUCTION = """You are an AI BI assistant connected to Apache Superset through MCP.
Use MCP tools to inspect real datasets, charts, dashboards, and metadata. Never invent
dataset names, columns, metrics, chart IDs, or dashboard IDs. Prefer read-only operations.
Do not request destructive database operations. If a tool fails, say so plainly.

Never create, update, save, or delete Superset assets. This phase only permits
read-only metadata discovery through the available MCP tools."""


NYC_TAXI_SCHEMA = """Available PostgreSQL analytics schema:

raw.yellow_taxi_trips
- vendor_id, tpep_pickup_datetime, tpep_dropoff_datetime, passenger_count
- trip_distance, ratecode_id, store_and_fwd_flag, pu_location_id, do_location_id
- payment_type, fare_amount, extra, mta_tax, tip_amount, tolls_amount
- improvement_surcharge, total_amount, congestion_surcharge, airport_fee
- cbd_congestion_fee, request_source, source_file, source_year, source_month, loaded_at

raw.taxi_zone_lookup
- location_id, borough, zone, service_zone

Join pickup zones with trip.pu_location_id = zone.location_id and dropoff zones
with trip.do_location_id = zone.location_id. The pickup timestamp is
tpep_pickup_datetime. payment_type is numeric (1 credit card, 2 cash, 3 no
charge, 4 dispute, 5 unknown, 0 flex fare)."""


class GeminiService:
    def __init__(self, api_key: str, model: str, *, answer_max_rows: int = 20) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.answer_max_rows = max(1, answer_max_rows)

    async def generate(self, contents: list[Any], tools: list[types.Tool]) -> Any:
        return await self.client.aio.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0,
                tools=tools,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )

    async def generate_sql(self, question: str) -> SQLGenerationResult:
        prompt = f"""You are a PostgreSQL analytics SQL generator.
Translate the user question into a plan. Return intent `data_query` only when
the question needs values computed from the database; otherwise return
`metadata_question` and an empty sql field.

For data_query, generate exactly ONE safe read-only PostgreSQL query.
Rules:
- Only SELECT or WITH ... SELECT. Never use modifying or administrative SQL.
- Use only the tables and columns in the supplied schema. Do not invent names.
- Prefer aggregates to raw trip records and use a reasonable LIMIT for ranking.
- For totals by the three loaded dataset months, prefer source_year and
  source_month; they reflect the imported files and are indexed. Use
  DATE_TRUNC only when the user specifically asks for calendar timestamps.
- `reasoning_summary` must be a short user-visible description, never hidden reasoning.

{NYC_TAXI_SCHEMA}

User question:
{question}"""
        return await self._structured_plan(prompt)

    async def classify_intent(self, message: str) -> IntentResult:
        prompt = f"""You are an intent router for an AI Business Intelligence assistant.
Your only job is to classify the user's request into exactly one intent and return
structured JSON matching the supplied schema. Do not provide chain-of-thought.

Available intents:
- ASK_DATA: retrieve, calculate, compare, aggregate, analyze, or explain data.
- CREATE_CHART: explicitly create or save a BI chart or visualization.
- CREATE_DASHBOARD: explicitly create a new dashboard.
- EDIT_CHART: modify an existing saved chart.
- EDIT_DASHBOARD: modify an existing dashboard.
- GENERAL: metadata, capabilities, datasets, charts, dashboards, or conversation
  that does not need analytical SQL or a BI asset change.

Rules:
1. Choose exactly one intent.
2. A temporary chart in chat is ASK_DATA. "Show" or "visualize" without an
   explicit create/save request is ASK_DATA.
3. CREATE_CHART and CREATE_DASHBOARD require explicit create/save language.
4. EDIT_* requires an existing asset to be modified.
5. If uncertain between ASK_DATA and CREATE_CHART, choose ASK_DATA.
6. Never invent target names or IDs. Set target_id to null; IDs are resolved by
   trusted application context.
7. `requires_confirmation` is true only for create/edit intents.

User message: {message}"""
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=IntentResult,
            ),
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, IntentResult):
            return parsed
        if isinstance(parsed, dict):
            return IntentResult.model_validate(parsed)
        return IntentResult.model_validate_json(response.text or "")

    async def generate_chart_plan(self, message: str) -> ChartPlan:
        prompt = f"""You are a BI chart planner. Convert the user's request into a
small semantic ChartPlan. Return JSON only and never include SQL, Superset API
payloads, form_data, datasource IDs, or hidden reasoning.

Allowed chart types: bar, line, pie, area.
Rules:
- Use bar for category comparisons, rankings, top-N, and bottom-N.
- Use line for time series; pie only for small part-to-whole distributions.
- Use area only when time-series magnitude emphasis is appropriate.
- Keep the title concise and user-friendly.
- `question` is a clear analytics question that can be sent to the existing
  PostgreSQL SQL generator.
- `metric` and `dimension` should be descriptive output-column names when
  evident, otherwise null. Do not invent database fields.
- `limit` is only for an explicitly requested top/bottom N, otherwise null.

Available PostgreSQL analytics schema:
{NYC_TAXI_SCHEMA}

User request: {message}"""
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=ChartPlan,
            ),
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, ChartPlan):
            return parsed
        if isinstance(parsed, dict):
            return ChartPlan.model_validate(parsed)
        return ChartPlan.model_validate_json(response.text or "")

    async def generate_dashboard_plan(self, message: str) -> DashboardPlan:
        prompt = f"""You are a BI dashboard planner for the NYC Yellow Taxi dataset.
Convert the user's request into a concise DashboardPlan with exactly 3 or 4
complementary charts. Return structured JSON only. Do not include SQL,
Superset payloads, layout JSON, IDs, or hidden reasoning.

Supported chart types: bar, line, pie.
Rules:
- Use line for time trends, bar for rankings/comparisons, and pie only for a
  small category distribution.
- Avoid redundant charts. Prefer a mix of trip trend, revenue trend, pickup
  behavior, and payment distribution for an overview request.
- Every chart needs a clear `question` for the existing SQL generator.
- Metric and dimension are descriptive output-column names when evident, not
  invented database fields. Use concise user-friendly titles.
- Do not include KPI/big-number charts or area charts.
- For a general NYC Taxi overview, use this vetted mix unless the user clearly
  asks otherwise: trips by month (line), revenue by month (line), top 10
  pickup zones (bar), and payment type distribution (pie). Use dimensions
  named `month`, `zone`, or `payment_type`; do not plan borough, hour, or
  day-of-week charts for this demo's saved physical dataset.

Available analytics schema:
{NYC_TAXI_SCHEMA}

User request: {message}"""
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=DashboardPlan,
            ),
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, DashboardPlan):
            return parsed
        if isinstance(parsed, dict):
            return DashboardPlan.model_validate(parsed)
        return DashboardPlan.model_validate_json(response.text or "")

    async def generate_edit_chart_plan(self, message: str) -> EditChartPlan:
        prompt = f"""You are a BI chart edit planner. Convert the request into exactly
one supported semantic edit operation and return structured JSON only.

Supported operations: CHANGE_CHART_TYPE, RENAME_CHART, CHANGE_METRIC,
CHANGE_DIMENSION.
Rules:
- Never invent a chart ID; chart_id must be null.
- Extract a chart_name only if the user explicitly gives one; otherwise null.
- Do not create SQL, Superset API payloads, form_data, datasource IDs, or
  settings not explicitly requested.
- CHANGE_CHART_TYPE only supports bar, line, pie. If another type is requested,
  preserve it as no operation is possible by selecting the closest supported
  operation only when the request is unambiguous.
- Preserve unrelated saved-chart settings.

User request: {message}"""
        return await self._edit_plan(prompt, EditChartPlan)

    async def generate_edit_dashboard_plan(self, message: str) -> EditDashboardPlan:
        prompt = f"""You are a BI dashboard edit planner. Convert the request into exactly
one supported semantic edit operation and return structured JSON only.

Supported operations: ADD_CHART, REMOVE_CHART, RENAME_DASHBOARD.
Rules:
- Never invent dashboard_id or chart_id; IDs must be null.
- Extract dashboard_name/chart_name only when explicitly stated.
- For a new chart to add, populate create_chart_plan with a compact ChartPlan.
  For an existing chart, use chart_name and leave create_chart_plan null.
- Do not create SQL, Superset API payloads, form_data, datasource IDs, layout
  JSON, or hidden reasoning.
- Preserve all unrelated dashboard settings.

Available analytics schema:
{NYC_TAXI_SCHEMA}

User request: {message}"""
        return await self._edit_plan(prompt, EditDashboardPlan)

    async def repair_sql(
        self, question: str, sql: str, database_error: str
    ) -> SQLGenerationResult:
        prompt = f"""Repair this failed PostgreSQL analytics query. Return a data_query
plan with exactly one safe SELECT or WITH ... SELECT query. Do not explain your
reasoning beyond a short reasoning_summary. Use only this schema:

{NYC_TAXI_SCHEMA}

Original question: {question}
Failed SQL: {sql}
PostgreSQL error: {database_error}
"""
        return await self._structured_plan(prompt)

    async def generate_answer_from_result(
        self, question: str, result: QueryResult
    ) -> str:
        prompt = f"""Answer the user's analytics question briefly in the same language as
the question. Use only the supplied query result; do not change, infer, or
round numbers unless the result already does so. If zero rows were returned,
say that no matching data was found. Do not mention internal prompts.

Question: {question}
SQL: {result.sql}
Columns: {result.columns}
Rows: {result.rows[:self.answer_max_rows]}
Row count: {result.row_count}
"""
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0),
        )
        return (response.text or "").strip()

    async def generate_visualization(
        self, question: str, result: QueryResult
    ) -> VisualizationSpec:
        prompt = f"""You are a BI visualization planner. Given an analytics question and
the query result, return one compact visualization plan.

Allowed types: none, bar, line, pie, area.
Rules:
- Use none for a single scalar, no rows, no meaningful numeric measure, or an unsuitable result.
- Use line for time series; bar for rankings/categorical comparisons; pie only for a small
  (at most eight category) part-to-whole distribution; area only for a time series where
  magnitude emphasis is useful.
- x_axis and y_axis must exactly match provided column names. y_axis must be numeric.
- Never invent columns. Return structured JSON only.

Question: {question}
Columns: {result.columns}
Rows (sample): {result.rows[:self.answer_max_rows]}
Row count: {result.row_count}
"""
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=VisualizationSpec,
            ),
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, VisualizationSpec):
            return parsed
        if isinstance(parsed, dict):
            return VisualizationSpec.model_validate(parsed)
        return VisualizationSpec.model_validate_json(response.text or "")

    async def _structured_plan(self, prompt: str) -> SQLGenerationResult:
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=SQLGenerationResult,
            ),
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, SQLGenerationResult):
            return parsed
        if isinstance(parsed, dict):
            return SQLGenerationResult.model_validate(parsed)
        return SQLGenerationResult.model_validate_json(response.text or "")

    async def _edit_plan(self, prompt: str, schema: type[Any]) -> Any:
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, schema):
            return parsed
        if isinstance(parsed, dict):
            return schema.model_validate(parsed)
        return schema.model_validate_json(response.text or "")
