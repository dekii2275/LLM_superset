"""Resolve trusted application permissions for Superset dashboard resources."""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

from app.services.superset import SupersetClient, SupersetEmbedError


class DashboardAccessService:
    def __init__(self, client: SupersetClient, user: dict[str, Any]) -> None:
        self.client = client
        self.user = user

    def dataset_clause(self, dataset_id: int) -> str | None:
        if self.user.get("role") == "admin":
            return None
        rules = [
            rule["filter_clause"].strip()
            for rule in self.user.get("rls_rules", [])
            if rule.get("dataset_id") == dataset_id and rule.get("filter_clause", "").strip()
        ]
        if not rules:
            raise HTTPException(
                status_code=403,
                detail=f"Tài khoản chưa được cấp quyền xem dataset {dataset_id} của dashboard này.",
            )
        dataset = self.client.get_dataset(dataset_id)
        columns = {column.get("column_name") for column in dataset.get("columns", [])}
        clauses = []
        for rule in rules:
            # The raw taxi dataset has a zone ID, whereas its virtual counterpart
            # exposes pickup_borough. Both must enforce the same pickup boundary.
            borough = re.fullmatch(r"pickup_borough\s*=\s*'((?:[^']|'')*)'", rule, re.I)
            if borough and "pickup_borough" not in columns:
                if (
                    dataset.get("table_name") != "yellow_taxi_trips"
                    or dataset.get("schema") != "raw"
                    or "pu_location_id" not in columns
                ):
                    raise HTTPException(
                        status_code=403, detail="Dataset không hỗ trợ quy tắc RLS này."
                    )
                rule = (
                    "pu_location_id IN (SELECT location_id FROM raw.taxi_zone_lookup "
                    f"WHERE borough = '{borough.group(1)}')"
                )
            clauses.append(f"({rule})")
        return " AND ".join(clauses)

    def chart_dataset_id(self, chart: dict[str, Any]) -> int:
        dataset_id = chart.get("datasource_id")
        if not dataset_id:
            context = self.client._json_object(chart.get("query_context"))
            dataset_id = (context.get("datasource") or {}).get("id")
        if not dataset_id:
            form_data = self.client._json_object(chart.get("form_data") or chart.get("params"))
            source = form_data.get("datasource")
            if isinstance(source, str) and re.fullmatch(r"\d+__table", source):
                dataset_id = source.split("__", 1)[0]
        if not dataset_id:
            raise SupersetEmbedError("Không xác định được dataset của biểu đồ để kiểm tra quyền.")
        return int(dataset_id)

    def dashboard(self, dashboard_ref: str | int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        dashboard = self.client.request("GET", f"/api/v1/dashboard/{dashboard_ref}").get("result")
        if not dashboard:
            raise HTTPException(status_code=404, detail="Không tìm thấy dashboard.")
        charts = self.client.request("GET", f"/api/v1/dashboard/{dashboard['id']}/charts").get(
            "result", []
        )
        if not charts:
            raise SupersetEmbedError("Dashboard không có biểu đồ để kiểm tra quyền.")
        rules = []
        dataset_ids = set()
        for chart in charts:
            try:
                dataset_id = self.chart_dataset_id(chart)
            except SupersetEmbedError:
                chart = self.client.request("GET", f"/api/v1/chart/{chart['id']}").get("result", {})
                dataset_id = self.chart_dataset_id(chart)
            if dataset_id in dataset_ids:
                continue
            dataset_ids.add(dataset_id)
            clause = self.dataset_clause(dataset_id)
            if clause:
                rules.append({"dataset": dataset_id, "clause": clause})
        return dashboard, rules

    def guest_token(self, dashboard_ref: str | int) -> str:
        dashboard, rules = self.dashboard(dashboard_ref)
        embedded_id = self.client.embedded_dashboard_id(str(dashboard["id"]))
        return self.client.create_guest_token(
            embedded_id, username=self.user["username"], rls=rules
        )

    def chart_guest_token(self, chart: dict[str, Any]) -> str:
        self.dataset_clause(self.chart_dataset_id(chart))
        for dashboard in chart.get("dashboards", []):
            dashboard_id = dashboard.get("id") if isinstance(dashboard, dict) else dashboard
            if not dashboard_id:
                continue
            try:
                return self.guest_token(int(dashboard_id))
            except HTTPException as error:
                if error.status_code != 403:
                    raise
        raise HTTPException(status_code=403, detail="Biểu đồ không thuộc dashboard được cấp quyền.")
