import logging
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.services.data_service import DataService
from app.services.schema_service import SchemaService
from app.services.superset import SupersetClient, SupersetEmbedError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/data", tags=["data"])


def get_superset_client() -> SupersetClient | None:
    if not settings.superset_admin_username or not settings.superset_admin_password:
        return None
    try:
        client = SupersetClient(
            settings.superset_url,
            settings.superset_admin_username,
            settings.superset_admin_password,
        )
        client.login()
        return client
    except SupersetEmbedError:
        return None


class DashboardSettingUpdate(BaseModel):
    dashboard_id: int | None = None
    is_enabled: bool = True


@router.post("/upload")
async def upload_dataset_file(
    file: UploadFile = File(...),
    table_name: str | None = Form(None),
    description: str | None = Form(None),
) -> dict[str, Any]:
    """Upload CSV or Parquet file, ingest into PostgreSQL raw schema, and register in Superset."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Không có tệp được chọn.")

    allowed_exts = (".csv", ".parquet", ".pq", ".txt")
    if not any(file.filename.lower().endswith(ext) for ext in allowed_exts):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ tệp định dạng .csv hoặc .parquet.")

    try:
        contents = await file.read()
        client = get_superset_client()
        data_svc = DataService(client)
        result = data_svc.upload_dataset(
            filename=file.filename,
            content=contents,
            table_name=table_name,
            description=description,
        )

        # Invalidate schema cache so the new dataset is visible immediately
        schema_svc = SchemaService(client)
        schema_svc.invalidate_cache()

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("dataset_upload_failed")
        raise HTTPException(status_code=500, detail=f"Lỗi khi xử lý tệp: {e}")


@router.get("/preview/{dataset_id}")
def preview_dataset_data(dataset_id: int, limit: int = 20) -> dict[str, Any]:
    """Preview first N rows of a dataset from PostgreSQL."""
    client = get_superset_client()
    schema_svc = SchemaService(client)
    dataset = schema_svc.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Không tìm thấy dataset.")

    table_name = dataset.get("table_name")
    if not table_name:
        raise HTTPException(status_code=404, detail="Dataset không có bảng tương ứng.")

    try:
        data_svc = DataService(client)
        return data_svc.preview_dataset(table_name=table_name, limit=limit)
    except Exception as e:
        logger.exception("dataset_preview_failed")
        raise HTTPException(status_code=500, detail=f"Không thể xem trước dữ liệu: {e}")


@router.get("/dashboards")
def list_dashboards() -> list[dict[str, Any]]:
    """List all available Superset dashboards for linking."""
    client = get_superset_client()
    data_svc = DataService(client)
    return data_svc.list_all_dashboards()


@router.put("/datasets/{dataset_id}/dashboard")
def update_dataset_dashboard(dataset_id: int, body: DashboardSettingUpdate) -> dict[str, Any]:
    """Toggle or update default dashboard for a dataset."""
    client = get_superset_client()
    data_svc = DataService(client)
    result = data_svc.update_dashboard_setting(
        dataset_id=dataset_id,
        dashboard_id=body.dashboard_id,
        is_enabled=body.is_enabled,
    )

    # Invalidate schema cache
    schema_svc = SchemaService(client)
    schema_svc.invalidate_cache()

    return result
