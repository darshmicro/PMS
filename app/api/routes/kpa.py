"""
KPA Master endpoints (spec Section 7). Reuses the M3 master_service for
the base CRUD/audit mechanics, adding weightage-bounds and effective-date
validation, and parent-reference checks for Department/Designation
applicability, before delegating.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.masters import Department, Designation
from app.models.performance_masters import KPAMaster
from app.schemas.kpa import KPACreate, KPAOut, KPAUpdate
from app.services import master_service as ms
from app.services.export_service import build_export_workbook
from app.services.kpa_kpi_service import validate_effective_dates, validate_weightage

router = APIRouter(prefix="/masters/kpa", tags=["kpa"])

KPA_CFG = ms.MasterFieldConfig(KPAMaster, "KPAID", "KPACode", "KPAName", "MASTERS.KPA")


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _to_out(k: KPAMaster) -> KPAOut:
    return KPAOut(
        kpa_id=k.KPAID, kpa_code=k.KPACode, kpa_name=k.KPAName, description=k.Description,
        department_id=k.DepartmentID, department_name=k.department.DeptName if k.department else None,
        designation_id=k.DesignationID,
        designation_name=k.designation.DesignationName if k.designation else None,
        category=k.Category, default_weightage=k.DefaultWeightage,
        effective_from=k.EffectiveFrom, effective_to=k.EffectiveTo, is_active=k.IsActive,
    )


def _check_parents(db: Session, department_id: int | None, designation_id: int | None) -> None:
    if department_id is not None and db.get(Department, department_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Department not found")
    if designation_id is not None and db.get(Designation, designation_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Designation not found")


@router.get("", response_model=list[KPAOut])
def list_kpas(
    search: str | None = None, active_only: bool | None = None, department_id: int | None = None,
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW")),
):
    rows = ms.list_records(db, KPA_CFG, search, active_only)
    if department_id is not None:
        rows = [r for r in rows if r.DepartmentID == department_id]
    return [_to_out(r) for r in rows]


@router.post("", response_model=KPAOut, status_code=status.HTTP_201_CREATED)
def create_kpa(
    payload: KPACreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    validate_weightage(payload.default_weightage, "Default Weightage")
    validate_effective_dates(payload.effective_from, payload.effective_to)
    _check_parents(db, payload.department_id, payload.designation_id)

    data = {
        "KPACode": payload.kpa_code, "KPAName": payload.kpa_name, "Description": payload.description,
        "DepartmentID": payload.department_id, "DesignationID": payload.designation_id,
        "Category": payload.category, "DefaultWeightage": payload.default_weightage,
        "EffectiveFrom": payload.effective_from, "EffectiveTo": payload.effective_to,
    }
    instance = ms.create_record(db, KPA_CFG, data, ctx, _client_ip(request))
    return _to_out(instance)


@router.put("/{kpa_id}", response_model=KPAOut)
def update_kpa(
    kpa_id: int, payload: KPAUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    existing = ms.get_record(db, KPA_CFG, kpa_id)
    update_fields = payload.model_dump(exclude={"reason"}, exclude_none=True)

    field_map = {
        "kpa_name": "KPAName", "description": "Description", "department_id": "DepartmentID",
        "designation_id": "DesignationID", "category": "Category",
        "default_weightage": "DefaultWeightage", "effective_from": "EffectiveFrom",
        "effective_to": "EffectiveTo",
    }
    orm_updates = {field_map[k]: v for k, v in update_fields.items()}

    weightage = orm_updates.get("DefaultWeightage", existing.DefaultWeightage)
    validate_weightage(weightage, "Default Weightage")
    eff_from = orm_updates.get("EffectiveFrom", existing.EffectiveFrom)
    eff_to = orm_updates.get("EffectiveTo", existing.EffectiveTo)
    validate_effective_dates(eff_from, eff_to)
    _check_parents(
        db, orm_updates.get("DepartmentID", existing.DepartmentID),
        orm_updates.get("DesignationID", existing.DesignationID),
    )

    instance = ms.update_record(db, KPA_CFG, kpa_id, orm_updates, ctx, _client_ip(request))
    return _to_out(instance)


@router.post("/{kpa_id}/deactivate", response_model=KPAOut)
def deactivate_kpa(
    kpa_id: int, reason: str, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    instance = ms.set_active_status(db, KPA_CFG, kpa_id, False, reason, ctx, _client_ip(request))
    return _to_out(instance)


@router.post("/{kpa_id}/activate", response_model=KPAOut)
def activate_kpa(
    kpa_id: int, reason: str, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    instance = ms.set_active_status(db, KPA_CFG, kpa_id, True, reason, ctx, _client_ip(request))
    return _to_out(instance)


@router.get("/export")
def export_kpas(db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW"))):
    rows = ms.list_records(db, KPA_CFG)
    content = build_export_workbook(
        sheet_title="KPA Master",
        headers=["KPA Code", "KPA Name", "Department", "Designation", "Category", "Default Weightage", "Active"],
        rows=[
            [
                r.KPACode, r.KPAName, r.department.DeptName if r.department else "",
                r.designation.DesignationName if r.designation else "", r.Category or "",
                r.DefaultWeightage if r.DefaultWeightage is not None else "", "Yes" if r.IsActive else "No",
            ]
            for r in rows
        ],
        generated_by=ctx.ad_username,
        context_label="Master Export - KPA",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=KPA_Master.xlsx"},
    )
