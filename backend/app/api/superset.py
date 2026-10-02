import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.schemas.ai import ChartExplanation, QueryResult, VisualizationSpec
from app.services.chart_explanation_service import (
    ChartExplanationService,
    _as_decimal,
    _format_number,
)
from app.services.gemini_service import GeminiService
from app.services.superset import SupersetClient, SupersetEmbedError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/superset", tags=["superset"])


def get_client() -> SupersetClient:
    if not settings.superset_admin_username or not settings.superset_admin_password:
        raise HTTPException(status_code=503, detail="Superset embed credentials are not configured.")
    client = SupersetClient(
        settings.superset_url,
        settings.superset_admin_username,
        settings.superset_admin_password,
    )
    try:
        client.login()
    except SupersetEmbedError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return client


@router.get("/embed-config")
def embed_config() -> dict[str, str]:
    client = get_client()
    try:
        dashboard_id = client.embedded_dashboard_id(settings.superset_dashboard_slug)
    except SupersetEmbedError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "dashboard_id": dashboard_id,
        "superset_url": settings.superset_public_url.rstrip("/"),
    }


@router.get("/guest-token")
def guest_token() -> dict[str, str]:
    client = get_client()
    try:
        dashboard_id = client.embedded_dashboard_id(settings.superset_dashboard_slug)
        token = client.create_guest_token(dashboard_id)
    except SupersetEmbedError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"token": token}


@router.get("/dashboard/{dashboard_id}/embed-config")
def dashboard_embed_config(dashboard_id: int) -> dict[str, str]:
    client = get_client()
    try:
        embedded_id = client.embedded_dashboard_id(str(dashboard_id))
    except SupersetEmbedError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"dashboard_id": embedded_id, "superset_url": settings.superset_public_url.rstrip("/")}


@router.get("/dashboard/{dashboard_id}/guest-token")
def dashboard_guest_token(dashboard_id: int) -> dict[str, str]:
    client = get_client()
    try:
        embedded_id = client.embedded_dashboard_id(str(dashboard_id))
        token = client.create_guest_token(embedded_id)
    except SupersetEmbedError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"token": token}


@router.get("/charts")
def list_dashboard_charts(dashboard_id: int | None = None) -> list[dict[str, Any]]:
    client = get_client()
    try:
        target_id = dashboard_id
        if not target_id:
            try:
                dash_res = client.request("GET", f"/api/v1/dashboard/{settings.superset_dashboard_slug}").get("result", {})
                target_id = dash_res.get("id")
            except Exception:
                target_id = None

        if target_id:
            raw_charts = client.request("GET", f"/api/v1/dashboard/{target_id}/charts").get("result", [])
        else:
            raw_charts = client.request("GET", "/api/v1/chart/?q=(page:0,page_size:100)").get("result", [])

        charts: list[dict[str, Any]] = []
        seen_ids = set()
        for item in raw_charts:
            chart_id = item.get("id")
            if not chart_id or chart_id in seen_ids:
                continue
            seen_ids.add(chart_id)
            form_data = item.get("form_data")
            if isinstance(form_data, str):
                try:
                    form_data = json.loads(form_data)
                except Exception:
                    form_data = {}
            elif not isinstance(form_data, dict):
                form_data = {}

            raw_viz = item.get("viz_type") or form_data.get("viz_type") or "bar"
            viz_type = "bar"
            if "line" in raw_viz:
                viz_type = "line"
            elif "pie" in raw_viz:
                viz_type = "pie"
            elif "area" in raw_viz:
                viz_type = "area"
            elif raw_viz == "big_number_total":
                viz_type = "kpi"

            charts.append({
                "id": chart_id,
                "slice_name": item.get("slice_name") or "Biểu đồ",
                "viz_type": viz_type,
                "raw_viz_type": raw_viz,
                "description": item.get("description") or "",
            })
        return charts
    except SupersetEmbedError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        logger.exception("list_dashboard_charts_failed")
        raise HTTPException(status_code=500, detail="Không thể tải danh sách biểu đồ từ Superset.") from error


@router.post("/charts/{chart_id}/explain")
async def explain_superset_chart(chart_id: int) -> dict[str, Any]:
    client = get_client()
    try:
        chart_res = client.request("GET", f"/api/v1/chart/{chart_id}").get("result", {})
        if not chart_res:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy biểu đồ ID {chart_id}.")

        chart_name = chart_res.get("slice_name") or "Biểu đồ"
        form_data = chart_res.get("params")
        if isinstance(form_data, str):
            try:
                form_data = json.loads(form_data)
            except Exception:
                form_data = {}
        elif not isinstance(form_data, dict):
            form_data = {}

        raw_viz = chart_res.get("viz_type") or form_data.get("viz_type") or ""

        # Fetch chart query data
        data_res = client.request("GET", f"/api/v1/chart/{chart_id}/data/").get("result", [])
        if not data_res:
            raise HTTPException(status_code=422, detail="Biểu đồ không trả về dữ liệu.")

        entry = data_res[0]
        data = entry.get("data", [])
        colnames = entry.get("colnames", [])
        sql = entry.get("query")

        explanation_service = ChartExplanationService()
        gemini = GeminiService(settings.gemini_api_key, settings.gemini_model) if settings.gemini_api_key else None

        # Handle KPI / big_number_total or 1 row with 1 col
        if raw_viz == "big_number_total" or (len(colnames) == 1 and len(data) == 1):
            metric_col = colnames[0] if colnames else (form_data.get("metric") or "Giá trị")
            raw_val = data[0].get(metric_col) if data else None
            dec_val = _as_decimal(raw_val)
            formatted = _format_number(dec_val) if dec_val is not None else str(raw_val)
            explanation = ChartExplanation(
                summary=f"Chỉ số {chart_name} hiện ghi nhận mức {formatted}.",
                highlights=[
                    f"Giá trị hiện tại: {formatted} ({metric_col}).",
                    "Chỉ số tổng hợp này phản ánh dữ liệu theo các điều kiện lọc đang áp dụng trên bảng điều khiển.",
                ],
                note="Dữ liệu được trích xuất trực tiếp từ Superset theo bộ lọc hiện hành của biểu đồ.",
            )
            if gemini:
                explanation = await explanation_service.explain_with_gemini(
                    base_explanation=explanation,
                    chart_title=chart_name,
                    viz_type="kpi",
                    sample_rows=data[:5],
                    gemini=gemini,
                )
            return {
                "chart_id": chart_id,
                "chart_name": chart_name,
                "viz_type": "kpi",
                "sql": sql,
                "explanation": explanation.model_dump(),
            }

        # Map to standard visualization type
        viz_type = "bar"
        if "line" in raw_viz:
            viz_type = "line"
        elif "pie" in raw_viz:
            viz_type = "pie"
        elif "area" in raw_viz:
            viz_type = "area"

        # Determine axes
        x_axis = None
        y_axis = None

        fd_x = form_data.get("x_axis") or (form_data.get("groupby") or [None])[0]
        if fd_x and fd_x in colnames:
            x_axis = fd_x

        fd_y = form_data.get("metric") or (form_data.get("metrics") or [None])[0]
        if isinstance(fd_y, dict):
            fd_y = fd_y.get("label")
        if fd_y and fd_y in colnames:
            y_axis = fd_y

        if not x_axis or not y_axis:
            num_cols = []
            cat_cols = []
            for col in colnames:
                is_num = any(_as_decimal(r.get(col)) is not None for r in data[:5])
                if is_num:
                    num_cols.append(col)
                else:
                    cat_cols.append(col)
            if not y_axis and num_cols:
                y_axis = num_cols[0]
            if not x_axis and cat_cols:
                x_axis = cat_cols[0]
            elif not x_axis and len(colnames) >= 2:
                x_axis = [c for c in colnames if c != y_axis][0]

        if not x_axis or not y_axis:
            raise HTTPException(status_code=422, detail="Không thể xác định các trục dữ liệu để phân tích biểu đồ.")

        qr = QueryResult(columns=colnames, rows=data, row_count=len(data))
        spec = VisualizationSpec(type=viz_type, x_axis=x_axis, y_axis=y_axis, title=chart_name)
        explanation = explanation_service.analyze(qr, spec)
        if gemini:
            explanation = await explanation_service.explain_with_gemini(
                base_explanation=explanation,
                chart_title=chart_name,
                viz_type=viz_type,
                sample_rows=data[:10],
                gemini=gemini,
            )
        return {
            "chart_id": chart_id,
            "chart_name": chart_name,
            "viz_type": viz_type,
            "sql": sql,
            "explanation": explanation.model_dump(),
        }
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("explain_superset_chart_failed chart_id=%s", chart_id)
        raise HTTPException(status_code=500, detail=f"Không thể phân tích biểu đồ: {error}") from error

