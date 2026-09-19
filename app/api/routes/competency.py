"""
Competency Master endpoints (spec Section 14). Simple code/name master
like the M3 org masters, plus weightage-bounds validation since
competency weightage feeds the same weighted-score formula as KPIs
(spec Section 13) and an out-of-range value would silently corrupt it.
"""
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.performance_masters import CompetencyMaster
from app.schemas.competency import CompetencyCreate, CompetencyOut, CompetencyUpdate
from app.services import master_service as ms
from app.services.export_service import build_export_workbook
from app.services.kpa_kpi_service import validate_weightage

router = APIRouter(prefix="/masters/competencies", tags=["competency"])

COMPETENCY_CFG = ms.MasterFieldConfig(
    CompetencyMaster, "CompetencyID", "CompetencyCode", "CompetencyName", "MASTERS.COMPETENCY"
)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("", response_model=list[CompetencyOut])
def list_competencies(
    search: str | None = None, active_only: bool | None = None, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW")),
):
    return ms.list_records(db, COMPETENCY_CFG, search, active_only)


@router.post("", response_model=CompetencyOut, status_code=status.HTTP_201_CREATED)
def create_competency(
    payload: CompetencyCreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    validate_weightage(payload.weightage)
    data = {
        "CompetencyCode": payload.competency_code, "CompetencyName": payload.competency_name,
        "Category": payload.category, "Weightage": payload.weightage,
    }
    return ms.create_record(db, COMPETENCY_CFG, data, ctx, _client_ip(request))


@router.put("/{competency_id}", response_model=CompetencyOut)
def update_competency(
    competency_id: int, payload: CompetencyUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    existing = ms.get_record(db, COMPETENCY_CFG, competency_id)
    weightage = payload.weightage if payload.weightage is not None else existing.Weightage
    validate_weightage(weightage)

    data = {
        k: v for k, v in {
            "CompetencyName": payload.competency_name, "Category": payload.category,
            "Weightage": payload.weightage,
        }.items() if v is not None
    }
    return ms.update_record(db, COMPETENCY_CFG, competency_id, data, ctx, _client_ip(request))


@router.post("/{competency_id}/deactivate", response_model=CompetencyOut)
def deactivate_competency(
    competency_id: int, reason: str, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    return ms.set_active_status(db, COMPETENCY_CFG, competency_id, False, reason, ctx, _client_ip(request))


@router.post("/{competency_id}/activate", response_model=CompetencyOut)
def activate_competency(
    competency_id: int, reason: str, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    return ms.set_active_status(db, COMPETENCY_CFG, competency_id, True, reason, ctx, _client_ip(request))


@router.get("/export")
def export_competencies(
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW"))
):
    rows = ms.list_records(db, COMPETENCY_CFG)
    content = build_export_workbook(
        sheet_title="Competency Master",
        headers=["Competency Code", "Competency Name", "Category", "Weightage", "Active"],
        rows=[
            [r.CompetencyCode, r.CompetencyName, r.Category or "",
             r.Weightage if r.Weightage is not None else "", "Yes" if r.IsActive else "No"]
            for r in rows
        ],
        generated_by=ctx.ad_username,
        context_label="Master Export - Competencies",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Competency_Master.xlsx"},
    )
