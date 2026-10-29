from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import AnalysisRecordCreate, AnalysisRecordOut, HistoryListResponse
from app.storage import delete_analysis_record, get_analysis_record, list_analysis_records, save_analysis_record

router = APIRouter(tags=["history"])


@router.post("/history", response_model=AnalysisRecordOut)
def create_history_record(payload: AnalysisRecordCreate) -> Dict[str, Any]:
    record = save_analysis_record(
        source=payload.source,
        analysis_type=payload.analysis_type,
        status=payload.status,
        token_count=payload.token_count,
        error_count=payload.error_count,
        result=payload.result,
        summary=payload.summary,
    )
    return record


@router.get("/history", response_model=HistoryListResponse)
def list_history_records(limit: int = Query(default=20, ge=1, le=100)) -> Dict[str, Any]:
    items = list_analysis_records(limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/history/{analysis_id}", response_model=AnalysisRecordOut)
def get_history_record(analysis_id: int) -> Dict[str, Any]:
    try:
        return get_analysis_record(analysis_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Analysis record {analysis_id} not found") from exc


@router.delete("/history/{analysis_id}")
def delete_history_record(analysis_id: int) -> Dict[str, Any]:
    if not delete_analysis_record(analysis_id):
        raise HTTPException(status_code=404, detail=f"Analysis record {analysis_id} not found")
    return {"deleted": True, "id": analysis_id}
