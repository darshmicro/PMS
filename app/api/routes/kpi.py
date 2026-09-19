"""
KPI Master endpoints (spec Section 8). Adds measurement-type validation,
weightage bounds, target ordering (Minimum <= Expected <= Stretch), and
KPA/Department/Designation parent-reference checks on top of the M3
master_service CRUD mechanics.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.masters import Department, Designation
from app.models.performance_masters import KPAMaster, KPIMaster
from app.schemas.kpi import KPICreate, KPIOut, KPIUpdate
from app.services import master_service as ms
from app.services.export_service import build_export_workbook
from app.services.kpa_kpi_service import (
    validate_measurement_type,
    validate_target_ordering,
    validate_weightage,
)

router = APIRouter(prefix="/masters/kpi", tags=["kpi"])

KPI_CFG = ms.MasterFieldConfig(KPIMaster, "KPIID", "KPICode", "KPIName", "MASTERS.KPI")


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _to_out(k: KPIMaster) -> KPIOut:
    return KPIOut(
        kpi_id=k.KPIID, kpi_code=k.KPICode, kpi_name=k.KPIName, description=k.Description,
        kpa_id=k.KPAID, kpa_name=k.kpa.KPAName if k.kpa else "",
        department_id=k.DepartmentID, department_name=k.department.DeptName if k.department else None,
        designation_id=k.DesignationID,
        designation_name=k.designation.DesignationName if k.designation else None,
        measurement_type=k.MeasurementType, unit=k.Unit, target_type=k.TargetType,
        default_target=k.DefaultTarget, minimum_target=k.MinimumTarget,
        expected_target=k.ExpectedTarget, stretch_target=k.StretchTarget,
        weightage=k.Weightage, scoring_method=k.ScoringMethod, is_active=k.IsActive,
    )


def _check_parents(db: Session, kpa_id: int, department_id: int | None, designation_id: int | None) -> None:
    if db.get(KPAMaster, kpa_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="KPA not found")
    if department_id is not None and db.get(Department, department_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Department not found")
    if designation_id is not None and db.get(Designation, designation_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Designation not found")


@router.get("", response_model=list[KPIOut])
def list_kpis(
    search: str | None = None, active_only: bool | None = None, kpa_id: int | None = None,
    department_id: int | None = None, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW")),
):
    rows = ms.list_records(db, KPI_CFG, search, active_only)
    if kpa_id is not None:
        rows = [r for r in rows if r.KPAID == kpa_id]
    if department_id is not None:
        rows = [r for r in rows if r.DepartmentID == department_id]
    return [_to_out(r) for r in rows]


@router.post("", response_model=KPIOut, status_code=status.HTTP_201_CREATED)
def create_kpi(
    payload: KPICreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    validate_measurement_type(payload.measurement_type)
    validate_weightage(payload.weightage)
    validate_target_ordering(payload.minimum_target, payload.expected_target, payload.stretch_target)
    _check_parents(db, payload.kpa_id, payload.department_id, payload.designation_id)

    data = {
        "KPICode": payload.kpi_code, "KPIName": payload.kpi_name, "Description": payload.description,
        "KPAID": payload.kpa_id, "DepartmentID": payload.department_id, "DesignationID": payload.designation_id,
        "MeasurementType": payload.measurement_type, "Unit": payload.unit, "TargetType": payload.target_type,
        "DefaultTarget": payload.default_target, "MinimumTarget": payload.minimum_target,
        "ExpectedTarget": payload.expected_target, "StretchTarget": payload.stretch_target,
        "Weightage": payload.weightage, "ScoringMethod": payload.scoring_method,
    }
    instance = ms.create_record(db, KPI_CFG, data, ctx, _client_ip(request))
    return _to_out(instance)


@router.put("/{kpi_id}", response_model=KPIOut)
def update_kpi(
    kpi_id: int, payload: KPIUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    existing = ms.get_record(db, KPI_CFG, kpi_id)
    update_fields = payload.model_dump(exclude={"reason"}, exclude_none=True)

    field_map = {
        "kpi_name": "KPIName", "description": "Description", "kpa_id": "KPAID",
        "department_id": "DepartmentID", "designation_id": "DesignationID",
        "measurement_type": "MeasurementType", "unit": "Unit", "target_type": "TargetType",
        "default_target": "DefaultTarget", "minimum_target": "MinimumTarget",
        "expected_target": "ExpectedTarget", "stretch_target": "StretchTarget",
        "weightage": "Weightage", "scoring_method": "ScoringMethod",
    }
    orm_updates = {field_map[k]: v for k, v in update_fields.items()}

    measurement_type = orm_updates.get("MeasurementType", existing.MeasurementType)
    validate_measurement_type(measurement_type)
    weightage = orm_updates.get("Weightage", existing.Weightage)
    validate_weightage(weightage)
    validate_target_ordering(
        orm_updates.get("MinimumTarget", existing.MinimumTarget),
        orm_updates.get("ExpectedTarget", existing.ExpectedTarget),
        orm_updates.get("StretchTarget", existing.StretchTarget),
    )
    _check_parents(
        db, orm_updates.get("KPAID", existing.KPAID),
        orm_updates.get("DepartmentID", existing.DepartmentID),
        orm_updates.get("DesignationID", existing.DesignationID),
    )

    instance = ms.update_record(db, KPI_CFG, kpi_id, orm_updates, ctx, _client_ip(request))
    return _to_out(instance)


@router.post("/{kpi_id}/deactivate", response_model=KPIOut)
def deactivate_kpi(
    kpi_id: int, reason: str, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    instance = ms.set_active_status(db, KPI_CFG, kpi_id, False, reason, ctx, _client_ip(request))
    return _to_out(instance)


@router.post("/{kpi_id}/activate", response_model=KPIOut)
def activate_kpi(
    kpi_id: int, reason: str, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    instance = ms.set_active_status(db, KPI_CFG, kpi_id, True, reason, ctx, _client_ip(request))
    return _to_out(instance)


@router.get("/export")
def export_kpis(db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW"))):
    rows = ms.list_records(db, KPI_CFG)
    content = build_export_workbook(
        sheet_title="KPI Master",
        headers=["KPI Code", "KPI Name", "KPA", "Measurement Type", "Unit", "Weightage",
                 "Min Target", "Expected Target", "Stretch Target", "Active"],
        rows=[
            [
                r.KPICode, r.KPIName, r.kpa.KPAName if r.kpa else "", r.MeasurementType, r.Unit or "",
                r.Weightage if r.Weightage is not None else "",
                r.MinimumTarget if r.MinimumTarget is not None else "",
                r.ExpectedTarget if r.ExpectedTarget is not None else "",
                r.StretchTarget if r.StretchTarget is not None else "",
                "Yes" if r.IsActive else "No",
            ]
            for r in rows
        ],
        generated_by=ctx.ad_username,
        context_label="Master Export - KPI",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=KPI_Master.xlsx"},
    )
