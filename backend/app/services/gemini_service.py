"""Gemini adapter; it receives MCP function definitions but no database secrets."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from google import genai
from google.genai import types

from app.schemas.ai import (
    ChartExplanation,
    ChartPlan,
    DashboardPlan,
    DashboardReport,
    EditChartPlan,
    EditDashboardPlan,
    IntentResult,
    QueryResult,
    SQLGenerationResult,
    VisualizationSpec,
)
from app.services.ai_settings import record_token_usage

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

logger = logging.getLogger(__name__)


class GeminiService:
    def __init__(self, api_key: str, model: str, *, answer_max_rows: int = 20) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.answer_max_rows = max(1, answer_max_rows)

    async def _generate_content(self, **kwargs: Any) -> Any:
        provider_call = self.client.aio.models.generate_content
        response = await provider_call(**kwargs)
        total_tokens = getattr(getattr(response, "usage_metadata", None), "total_token_count", None)
        if total_tokens is not None:
            try:
                await asyncio.to_thread(record_token_usage, int(total_tokens))
            except Exception:
                logger.warning("gemini_token_usage_record_failed", exc_info=True)
        return response

    async def generate(self, contents: list[Any], tools: list[types.Tool]) -> Any:
        return await self._generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0,
                tools=tools,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )

    async def generate_sql(
        self,
        question: str,
        schema_context: str | None = None,
        last_sql: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        force_data_query: bool = False,
    ) -> SQLGenerationResult:
        active_schema = schema_context or NYC_TAXI_SCHEMA
        history_context = ""
        if last_sql:
            history_context += f"\nPrevious SQL executed:\n```sql\n{last_sql}\n```\n"
        if conversation_history:
            history_lines = [
                f"{m.get('role', 'user')}: {m.get('content', '')}"
                for m in conversation_history[-8:]
            ]
            history_context += "\nRecent conversation context:\n" + "\n".join(history_lines) + "\n"

        intent_instruction = (
            "This request is for data rows to render a chart. Return intent `data_query` "
            "and a nonempty SQL query. The chart title and instructions are not a "
            "metadata question."
            if force_data_query
            else "Return intent `data_query` only when the question needs values computed "
            "from the database; otherwise return `metadata_question` and an empty sql field."
        )
        prompt = f"""You are a PostgreSQL analytics SQL generator.
Translate the user question into a plan. {intent_instruction}

For data_query, generate exactly ONE safe read-only PostgreSQL query.
Rules:
- Only SELECT or WITH ... SELECT. Never use modifying or administrative SQL.
- Use only the tables and columns in the supplied schema. Do not invent names.
- Prefer aggregates to raw records and use a reasonable LIMIT for ranking.
- If predefined metrics exist in the schema, follow their expressions or logic.
- If a previous SQL query or conversation history is provided and the user's question is a follow-up refinement (e.g. adding a WHERE filter, changing grouping/time grain, or drilling down), ACCUMULATE AND REFINE upon the previous query instead of starting from scratch!
- `reasoning_summary` must be a short user-visible description, never hidden reasoning.

{active_schema}
{history_context}
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
        response = await self._generate_content(
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

    async def generate_chart_plan(
        self, message: str, schema_context: str | None = None
    ) -> ChartPlan:
        active_schema = schema_context or NYC_TAXI_SCHEMA
        prompt = f"""You are a BI chart planner. Convert the user's request into a
small semantic ChartPlan. Return JSON only and never include SQL, Superset API
payloads, form_data, datasource IDs, or hidden reasoning.

Allowed chart types: bar, line, pie, area, kpi, table, map, heatmap.
Rules:
- Use kpi for a single high-level scalar aggregate metric (e.g., Total Revenue, Total Trips, Average Amount).
- Use bar for category comparisons, rankings, top-N, and bottom-N.
- Use line for time series; area for volume or cumulative trend over time.
- Use pie only for small part-to-whole distributions (<= 7 categories).
- Use table for detailed multi-column records or rankings.
- Use heatmap for a metric across TWO categorical dimensions. Set `dimension`
  to the X category, `secondary_dimension` to the Y category, and `metric` to
  the aggregate. The question must request both categories and the metric.
- Use map with `map_style="grid"` only when the user explicitly requests
  deck.gl Grid or a 3D grid map. Request individual latitude/longitude rows;
  the grid chart aggregates points spatially.
- Keep the title concise and user-friendly.
- `question` is a clear analytics question that can be sent to the existing
  PostgreSQL SQL generator.
- `metric` and `dimension` should be descriptive output-column names when
  evident, otherwise null. Do not invent database fields.
- `limit` is only for an explicitly requested top/bottom N, otherwise null.

Available PostgreSQL analytics schema:
{active_schema}

User request: {message}"""
        response = await self._generate_content(
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

    async def generate_dashboard_plan(
        self, message: str, schema_context: str | None = None
    ) -> DashboardPlan:
        active_schema = schema_context or NYC_TAXI_SCHEMA
        prompt = f"""You are an executive BI dashboard planner.
Convert the user's request into a professional, structured DashboardPlan with 2 to 8
complementary charts adhering to the Executive Layout Hierarchy:
- Tier 1: 1 or 2 `kpi` cards for key headline metrics (e.g. Total Count, Maximum Value, Average Value).
- Tier 2: 1 `map` chart if geographic or spatial columns (latitude, longitude, country, iso) are present.
- Tier 3: 1 `line` or `area` chart for primary time-series trends (if timestamp/date fields exist).
- Tier 4: 1 to 3 `bar` or `pie` charts for category comparisons, breakdowns, or distributions.
- Tier 4: Add a `heatmap` when the user asks for one and two useful categories exist.
- Tier 5: 1 `table` for detailed record inspection if appropriate.

Supported chart types: kpi, bar, line, pie, area, table, map, heatmap.
Total chart count must be between 2 and 8. Honor an explicit minimum chart count.
Rules:
- Prefer a cohesive executive overview combining KPI summary cards, map/trends, and categorical breakdowns.
- Every chart needs a clear `question` for the existing SQL generator.
- For heatmap, specify `dimension` (X category), `secondary_dimension` (Y
  category), and `metric` (numeric aggregate); request all three in its question.
- Include every chart type the user explicitly requires, especially maps and heatmaps.
- Metric and dimension must strictly match real columns from the available schema. Never invent non-existent database fields.
- If the user asks for concepts not present in the dataset (e.g. pollution/air quality when the schema only has city populations), adapt gracefully using available relevant columns (e.g. population_max, is_megacity, country) rather than failing.
- Return structured JSON only. Do not include SQL, Superset payloads, layout JSON, IDs, or hidden reasoning.

Available analytics schema:
{active_schema}

User request: {message}"""
        response = await self._generate_content(
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

    async def generate_edit_dashboard_plan(
        self, message: str, schema_context: str | None = None
    ) -> EditDashboardPlan:
        active_schema = schema_context or NYC_TAXI_SCHEMA
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
{active_schema}

User request: {message}"""
        return await self._edit_plan(prompt, EditDashboardPlan)

    async def repair_sql(
        self, question: str, sql: str, database_error: str, schema_context: str | None = None
    ) -> SQLGenerationResult:
        active_schema = schema_context or NYC_TAXI_SCHEMA
        prompt = f"""Repair this failed PostgreSQL analytics query. Return a data_query
plan with exactly one safe SELECT or WITH ... SELECT query. Do not explain your
reasoning beyond a short reasoning_summary. Use only this schema:

{active_schema}

Original question: {question}
Failed SQL: {sql}
PostgreSQL error: {database_error}
"""
        return await self._structured_plan(prompt)

    async def generate_answer_from_result(self, question: str, result: QueryResult) -> str:
        prompt = f"""Answer the user's analytics question briefly in the same language as
the question. Use only the supplied query result; do not change, infer, or
round numbers unless the result already does so. If zero rows were returned,
say that no matching data was found. Do not mention internal prompts.

Question: {question}
SQL: {result.sql}
Columns: {result.columns}
Rows: {result.rows[: self.answer_max_rows]}
Row count: {result.row_count}
"""
        response = await self._generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0),
        )
        return (response.text or "").strip()

    async def generate_dashboard_report(
        self,
        dashboard_title: str,
        charts: list[dict[str, Any]],
        *,
        active_tab_title: str = "",
        applied_filters: list[str] | None = None,
    ) -> DashboardReport:
        prompt = f"""Create a Vietnamese business report for the Superset dashboard "{dashboard_title}".
Use only the supplied chart results. Do not invent facts, values, causes, or recommendations.
Return a concise overview, at most five evidence-backed highlights, and exactly one
chart_insights entry for every supplied chart_id. Each insight must be one or two sentences
about that chart. Mention if its data is unavailable or only a sample. Keep chart_id values
exactly as supplied.

Active tab: {active_tab_title or "Dashboard"}
Selected dashboard filters: {"; ".join(applied_filters or []) or "none"}

Dashboard chart results (rows may be truncated to a sample):
{json.dumps(charts, ensure_ascii=False, default=str)}"""
        response = await self._generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=DashboardReport,
            ),
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, DashboardReport):
            return parsed
        if isinstance(parsed, dict):
            return DashboardReport.model_validate(parsed)
        return DashboardReport.model_validate_json(response.text or "")

    async def generate_visualization(self, question: str, result: QueryResult) -> VisualizationSpec:
        prompt = f"""You are a BI visualization planner. Given an analytics question and
the query result, return one compact visualization plan.

Allowed types: none, bar, line, pie, area, map, table, kpi, heatmap.
Rules:
- Use none for a single scalar or an unsuitable result.
- Use map if coordinates (latitude, longitude) or country codes are present in the query result.
- Use kpi for a single headline metric or total.
- Use line for time series; bar for rankings/categorical comparisons; pie only for a small
  (at most eight category) part-to-whole distribution; area only for a time series where
  magnitude emphasis is useful; table for detailed record lists.
- x_axis and y_axis must match provided column names when applicable.
- For heatmap, x_axis and y_axis are the two categories and value_axis is numeric.
- Never invent columns. Return structured JSON only.

Question: {question}
Columns: {result.columns}
Rows (sample): {result.rows[: self.answer_max_rows]}
Row count: {result.row_count}
"""
        response = await self._generate_content(
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
        response = await self._generate_content(
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
        response = await self._generate_content(
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

    async def generate_chart_explanation(
        self,
        chart_title: str,
        viz_type: str,
        computed_summary: str,
        computed_highlights: list[str],
        computed_note: str,
        sample_data: list[dict[str, Any]],
    ) -> ChartExplanation:
        prompt = f"""You are a senior Business Intelligence (BI) expert and data strategist.
Given verified statistical calculations and sample records from an analytics database query, produce a professional, insightful executive explanation of the chart in Vietnamese (tiếng Việt).

Chart Title: {chart_title}
Visualization Type: {viz_type}
Base Statistical Summary: {computed_summary}
Base Key Metrics & Extremes: {computed_highlights}
Scope Note: {computed_note}
Sample Records: {sample_data[:10]}

Instructions:
1. Ground all numbers and observations strictly in the provided facts and data. Do NOT hallucinate unobserved metrics or external causes (e.g. weather, traffic incidents) unless present in the data.
2. `summary`: Write 1-2 fluent, insightful sentences summarizing the overarching business story, distribution, or performance pattern.
3. `highlights`: Provide 2-4 compelling bullet points highlighting key business observations (e.g. market dominance, concentration of trips, disparities between groups, peak periods, or notable momentum). Include concrete numbers from the provided facts.
4. `note`: State the data coverage and limitations clearly.
5. Return JSON conforming to the ChartExplanation schema."""

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=ChartExplanation,
            ),
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, ChartExplanation):
            return parsed
        if isinstance(parsed, dict):
            return ChartExplanation.model_validate(parsed)
        return ChartExplanation.model_validate_json(response.text or "")
