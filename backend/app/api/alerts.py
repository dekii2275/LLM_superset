from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.anomaly_service import AnomalyService

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


class AlertItem(BaseModel):
    id: int
    dataset_id: int | None = None
    alert_type: str
    severity: str
    title: str
    message: str
    metric_name: str | None = None
    change_percent: float | None = None
    suggested_query: str | None = None
    is_read: bool = False
    created_at: str | None = None


class AlertsResponse(BaseModel):
    alerts: list[AlertItem]
    unread_count: int


@router.get("", response_model=AlertsResponse)
def get_alerts(limit: int = 20) -> AlertsResponse:
    """Fetch recent system alerts and unread count."""
    alerts_data = AnomalyService.get_alerts(limit=limit)
    unread = sum(1 for a in alerts_data if not a["is_read"])
    return AlertsResponse(
        alerts=[AlertItem(**a) for a in alerts_data],
        unread_count=unread,
    )


@router.post("/scan")
def trigger_scan(dataset_id: int = 1) -> dict[str, Any]:
    """Manually trigger anomaly detection scan on dataset."""
    new_alerts = AnomalyService.scan_anomalies(dataset_id=dataset_id)
    return {
        "status": "success",
        "new_alerts_detected": len(new_alerts),
        "alerts": new_alerts,
    }


@router.post("/{alert_id}/read")
def mark_read(alert_id: int) -> dict[str, Any]:
    """Mark a single alert as read."""
    success = AnomalyService.mark_as_read(alert_id)
    return {"status": "success" if success else "failed"}


@router.post("/read-all")
def mark_all_read() -> dict[str, Any]:
    """Mark all alerts as read."""
    success = AnomalyService.mark_all_as_read()
    return {"status": "success" if success else "failed"}
