import logging

from fastapi import APIRouter, HTTPException, Query

from app.services.semantic_service import (
    BusinessGlossaryItem,
    SemanticService,
    VerifiedMetricItem,
)

router = APIRouter(prefix="/api/v1/semantic", tags=["semantic"])
logger = logging.getLogger(__name__)


@router.get("/glossary", response_model=list[BusinessGlossaryItem])
def get_glossary(dataset_id: int | None = Query(default=None)) -> list[BusinessGlossaryItem]:
    """Retrieve glossary terms, optionally filtered by dataset_id."""
    try:
        return SemanticService.get_glossary(dataset_id)
    except Exception as e:
        logger.error(f"Failed to fetch glossary: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch glossary") from e


@router.post("/glossary", response_model=BusinessGlossaryItem)
def add_glossary_term(item: BusinessGlossaryItem) -> BusinessGlossaryItem:
    """Add a new business glossary synonym / term."""
    try:
        return SemanticService.add_glossary_term(item)
    except Exception as e:
        logger.error(f"Failed to add glossary term: {e}")
        raise HTTPException(status_code=500, detail="Failed to add glossary term") from e


@router.delete("/glossary/{term_id}")
def delete_glossary_term(term_id: int) -> dict[str, bool]:
    """Delete a glossary term by ID."""
    success = SemanticService.delete_glossary_term(term_id)
    if not success:
        raise HTTPException(status_code=404, detail="Glossary term not found")
    return {"success": True}


@router.get("/metrics", response_model=list[VerifiedMetricItem])
def get_verified_metrics(dataset_id: int | None = Query(default=None)) -> list[VerifiedMetricItem]:
    """Retrieve verified metrics (Golden SQL), optionally filtered by dataset_id."""
    try:
        return SemanticService.get_verified_metrics(dataset_id)
    except Exception as e:
        logger.error(f"Failed to fetch verified metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch verified metrics") from e


@router.post("/metrics", response_model=VerifiedMetricItem)
def add_verified_metric(item: VerifiedMetricItem) -> VerifiedMetricItem:
    """Add a new verified metric definition."""
    try:
        return SemanticService.add_verified_metric(item)
    except Exception as e:
        logger.error(f"Failed to add verified metric: {e}")
        raise HTTPException(status_code=500, detail="Failed to add verified metric") from e


@router.delete("/metrics/{metric_id}")
def delete_verified_metric(metric_id: int) -> dict[str, bool]:
    """Delete a verified metric by ID."""
    success = SemanticService.delete_verified_metric(metric_id)
    if not success:
        raise HTTPException(status_code=404, detail="Verified metric not found")
    return {"success": True}
