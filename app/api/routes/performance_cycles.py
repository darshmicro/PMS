"""
Performance Cycle endpoints (spec Section 9). HR/Plant Head/MD/HR Admin
create and edit; everyone can view (dashboards need to know the active
cycle and its stage dates). Every date change is validated against the
full stage timeline before being saved (performance_cycle_service.py).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.performance_masters import PerformanceCycle
from app.schemas.performance_cycle import (
    CYCLE_FIELD_MAP,
    PerformanceCycleCreate,
    PerformanceCycleOut,
    PerformanceCycleUpdate,
)
from app.services.audit_service import write_audit
from app.services.export_service import build_export_workbook
from app.services.performance_cycle_service import validate_cycle_dates

router = APIRouter(prefix="/masters/performance-cycles", tags=["performance-cycles"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _to_out(c: PerformanceCycle) -> PerformanceCycleOut:
    return PerformanceCycleOut(
        cycle_id=c.CycleID, cycle_name=c.CycleName, year=c.Year,
        kpi_setting_start=c.KPISettingStart, kpi_setting_end=c.KPISettingEnd,
        self_assessment_start=c.SelfAssessmentStart, self_assessment_end=c.SelfAssessmentEnd,
        manager_review_start=c.ManagerReviewStart, manager_review_end=c.ManagerReviewEnd,
        hod_review_start=c.HODReviewStart, hod_review_end=c.HODReviewEnd,
        hr_review_start=c.HRReviewStart, hr_review_end=c.HRReviewEnd,
        plant_head_approval_start=c.PlantHeadApprovalStart, plant_head_approval_end=c.PlantHeadApprovalEnd,
        md_approval_start=c.MDApprovalStart, md_approval_end=c.MDApprovalEnd,
        is_active=c.IsActive,
    )


@router.get("", response_model=list[PerformanceCycleOut])
def list_cycles(
    active_only: bool | None = None, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW")),
):
    query = db.query(PerformanceCycle)
    if active_only is not None:
        query = query.filter(PerformanceCycle.IsActive == active_only)
    return [_to_out(c) for c in query.order_by(PerformanceCycle.CycleName.desc()).all()]


@router.post("", response_model=PerformanceCycleOut, status_code=status.HTTP_201_CREATED)
def create_cycle(
    payload: PerformanceCycleCreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    if db.query(PerformanceCycle).filter(PerformanceCycle.CycleName == payload.cycle_name).one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A cycle with this name already exists")

    data = payload.model_dump()
    merged = {CYCLE_FIELD_MAP[k]: v for k, v in data.items()}
    validate_cycle_dates(merged)

    cycle = PerformanceCycle(**merged)
    db.add(cycle)
    db.commit()
    db.refresh(cycle)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="CREATE", module="PERFORMANCE_CYCLE", record_id=str(cycle.CycleID),
        new_value=str(merged), ip_address=_client_ip(request),
    )
    return _to_out(cycle)


@router.put("/{cycle_id}", response_model=PerformanceCycleOut)
def update_cycle(
    cycle_id: int, payload: PerformanceCycleUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    cycle = db.get(PerformanceCycle, cycle_id)
    if cycle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Performance cycle not found")

    update_fields = payload.model_dump(exclude={"reason"}, exclude_none=True)
    orm_updates = {CYCLE_FIELD_MAP[k]: v for k, v in update_fields.items()}

    # Merge onto the cycle's FULL current timeline so a single-stage edit
    # is validated in the context of every other stage's dates, not just
    # the field being changed (see performance_cycle_service docstring).
    full_state = {col: getattr(cycle, col) for col in CYCLE_FIELD_MAP.values() if col != "CycleName"}
    full_state.update(orm_updates)
    validate_cycle_dates(full_state)

    old_value = {col: getattr(cycle, col) for col in orm_updates}
    for col, value in orm_updates.items():
        setattr(cycle, col, value)
    db.commit()
    db.refresh(cycle)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="EDIT", module="PERFORMANCE_CYCLE", record_id=str(cycle_id),
        old_value=str(old_value), new_value=str(orm_updates), reason=payload.reason,
        ip_address=_client_ip(request),
    )
    return _to_out(cycle)


@router.post("/{cycle_id}/deactivate", response_model=PerformanceCycleOut)
def deactivate_cycle(
    cycle_id: int, reason: str, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    cycle = db.get(PerformanceCycle, cycle_id)
    if cycle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Performance cycle not found")
    cycle.IsActive = False
    db.commit()

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="DEACTIVATE", module="PERFORMANCE_CYCLE", record_id=str(cycle_id),
        reason=reason, ip_address=_client_ip(request),
    )
    return _to_out(cycle)


@router.get("/export")
def export_cycles(db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW"))):
    rows = db.query(PerformanceCycle).order_by(PerformanceCycle.CycleName.desc()).all()
    content = build_export_workbook(
        sheet_title="Performance Cycles",
        headers=["Cycle Name", "KPI Setting", "Self Assessment", "Manager Review", "HOD Review",
                 "HR Review", "Plant Head Approval", "MD Approval", "Active"],
        rows=[
            [
                c.CycleName,
                f"{c.KPISettingStart or ''} to {c.KPISettingEnd or ''}",
                f"{c.SelfAssessmentStart or ''} to {c.SelfAssessmentEnd or ''}",
                f"{c.ManagerReviewStart or ''} to {c.ManagerReviewEnd or ''}",
                f"{c.HODReviewStart or ''} to {c.HODReviewEnd or ''}",
                f"{c.HRReviewStart or ''} to {c.HRReviewEnd or ''}",
                f"{c.PlantHeadApprovalStart or ''} to {c.PlantHeadApprovalEnd or ''}",
                f"{c.MDApprovalStart or ''} to {c.MDApprovalEnd or ''}",
                "Yes" if c.IsActive else "No",
            ]
            for c in rows
        ],
        generated_by=ctx.ad_username,
        context_label="Master Export - Performance Cycles",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Performance_Cycles_Master.xlsx"},
    )
