"""
KPA/KPI Assignment endpoints (spec Section 10). "Manager/HR can assign
KPAs and KPIs to employees" - visibility and edit rights follow the same
role-scoping pattern as the Employee Master (M4): a Manager can only see
and assign for their own direct reports, a HOD their department, and
HR/Plant Head/MD/HR Administrator see and can assign for everyone (spec
Section 4: Plant Head and MD have full business-level admin rights).

DESIGN NOTE on ASSIGNMENT.PROPOSE (Employee self-service): an Employee
also holds a second, narrower permission, ASSIGNMENT.PROPOSE, alongside
Manager/HR's ASSIGNMENT.EDIT, on the mutating endpoints below (create
assignment, add/edit/remove KPA, add/edit/remove KPI) - see
require_any_permission() calls. It grants nothing ASSIGNMENT.EDIT
doesn't already grant Manager/HR: _get_scoped_performance's existing
_apply_scope() restricts a plain EMPLOYEE-role caller to their own
EmployeeID regardless of which of the two permissions let them in, so an
employee can only ever create or edit their own appraisal record. The
"propose" half of "Employee proposes, Manager approves" is exactly that
narrower scope; the "Manager approves" half needs no new status field or
workflow state at all - it reuses the DRAFT status's existing edit
window. ensure_editable() already refuses any change once an assignment
leaves DRAFT, and only a Manager/HR/Plant Head/MD/HR Admin holding
ASSIGNMENT.EDIT can call POST /{id}/submit to move it out of DRAFT (an
Employee's ASSIGNMENT.PROPOSE does not grant that route - it isn't
listed there). So an employee-proposed KPA/KPI sits in the same DRAFT
record a Manager can see, edit or remove entries from, and it only
becomes real - moving to KPI_ASSIGNED and starting the self-assessment
window - once that Manager reviews it and submits. No schema migration
needed.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_any_permission, require_permission
from app.db.base import get_db
from app.models.assignment import DRAFT, KPI_ASSIGNED, EmployeeKPA, EmployeeKPI, EmployeePerformance
from app.models.employee import Employee
from app.models.performance_masters import KPAMaster, KPIMaster, PerformanceCycle
from app.schemas.assignment import (
    AssignmentCreate,
    AssignmentOut,
    EmployeeKPACreate,
    EmployeeKPAOut,
    EmployeeKPICreate,
    EmployeeKPIOut,
    EmployeeKPIUpdate,
)
from app.services.assignment_service import (
    check_duplicate_kpi,
    ensure_editable,
    recompute_rollups,
    validate_row_weightage,
    validate_submission_ready,
    validate_target,
)
from app.services.audit_service import write_audit
from app.services.export_service import build_export_workbook

router = APIRouter(prefix="/assignments", tags=["assignments"])

BROAD_ACCESS_ROLES = {"HR", "HR_ADMIN", "PLANT_HEAD", "MD", "SYS_ADMIN"}


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _kpi_to_out(k: EmployeeKPI) -> EmployeeKPIOut:
    return EmployeeKPIOut(
        employee_kpi_id=k.EmployeeKPIID, kpi_id=k.KPIID, kpi_name=k.kpi.KPIName,
        description=k.Description, target=k.Target, unit=k.Unit, measurement_type=k.MeasurementType,
        weightage=k.Weightage, due_date=k.DueDate, evidence_required=k.EvidenceRequired,
    )


def _kpa_to_out(ek: EmployeeKPA) -> EmployeeKPAOut:
    return EmployeeKPAOut(
        employee_kpa_id=ek.EmployeeKPAID, kpa_id=ek.KPAID, kpa_name=ek.kpa.KPAName,
        weightage=ek.Weightage, kpis=[_kpi_to_out(k) for k in ek.kpis],
    )


def _to_out(p: EmployeePerformance) -> AssignmentOut:
    return AssignmentOut(
        performance_id=p.PerformanceID, employee_id=p.EmployeeID, employee_name=p.employee.FullName,
        cycle_id=p.CycleID, cycle_name=p.cycle.CycleName, status=p.Status,
        total_weightage=p.TotalWeightage, is_locked=p.IsLocked,
        kpas=[_kpa_to_out(ek) for ek in p.kpas], created_at=p.CreatedAt,
    )


def _apply_scope(query, ctx: CurrentContext):
    """Mirrors employees.py::_apply_scope, applied via a join from
    Employee_Performance to Employees so the same visibility rule governs
    both the Employee Master and its appraisals."""
    if BROAD_ACCESS_ROLES & set(ctx.role_codes):
        return query
    query = query.join(Employee, EmployeePerformance.EmployeeID == Employee.EmployeeID)
    if "HOD" in ctx.role_codes:
        return query.filter(Employee.HODID == ctx.employee_id)
    if "MANAGER" in ctx.role_codes:
        return query.filter(Employee.ManagerID == ctx.employee_id)
    return query.filter(Employee.EmployeeID == ctx.employee_id)


def _employee_in_scope(employee: Employee, ctx: CurrentContext) -> bool:
    """Direct-object counterpart to _apply_scope's role check, for a caller
    that already holds the Employee row (create_assignment's own-scope
    check) rather than a query to filter. _apply_scope above is built for
    queries whose base entity is EmployeePerformance - it joins Employee in
    - so calling it against a bare `db.query(Employee)` (as create_assignment
    used to) leaves that join with nothing to attach to, which SQLAlchemy
    reports as "Don't know how to join to <Employee>". Checking the already
    -fetched Employee object's own columns directly avoids the join
    entirely."""
    if BROAD_ACCESS_ROLES & set(ctx.role_codes):
        return True
    if "HOD" in ctx.role_codes:
        return employee.HODID == ctx.employee_id
    if "MANAGER" in ctx.role_codes:
        return employee.ManagerID == ctx.employee_id
    return employee.EmployeeID == ctx.employee_id


def _get_scoped_performance(db: Session, performance_id: int, ctx: CurrentContext) -> EmployeePerformance:
    query = _apply_scope(db.query(EmployeePerformance).filter(EmployeePerformance.PerformanceID == performance_id), ctx)
    performance = query.one_or_none()
    if performance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found or outside your access scope")
    return performance


@router.get("", response_model=list[AssignmentOut])
def list_assignments(
    employee_id: int | None = None, cycle_id: int | None = None, status_filter: str | None = None,
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("ASSIGNMENT.VIEW")),
):
    query = _apply_scope(db.query(EmployeePerformance), ctx)
    if employee_id is not None:
        query = query.filter(EmployeePerformance.EmployeeID == employee_id)
    if cycle_id is not None:
        query = query.filter(EmployeePerformance.CycleID == cycle_id)
    if status_filter is not None:
        query = query.filter(EmployeePerformance.Status == status_filter)
    return [_to_out(p) for p in query.all()]


@router.get("/{performance_id}", response_model=AssignmentOut)
def get_assignment(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("ASSIGNMENT.VIEW")),
):
    return _to_out(_get_scoped_performance(db, performance_id, ctx))


@router.post("", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_any_permission("ASSIGNMENT.EDIT", "ASSIGNMENT.PROPOSE")),
):
    employee = db.get(Employee, payload.employee_id)
    if employee is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Employee not found")
    cycle = db.get(PerformanceCycle, payload.cycle_id)
    if cycle is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Performance cycle not found")

    # Confirm this employee is within the caller's assignment scope (a
    # Manager may only start an assignment for their own direct reports).
    if not _employee_in_scope(employee, ctx):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="This employee is outside your assignment scope")

    existing = (
        db.query(EmployeePerformance)
        .filter(EmployeePerformance.EmployeeID == payload.employee_id, EmployeePerformance.CycleID == payload.cycle_id)
        .one_or_none()
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="An assignment already exists for this employee and cycle")

    performance = EmployeePerformance(EmployeeID=payload.employee_id, CycleID=payload.cycle_id, Status=DRAFT)
    db.add(performance)
    db.commit()
    db.refresh(performance)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="CREATE", module="KPA_KPI_ASSIGNMENT", record_id=str(performance.PerformanceID),
        new_value=f"EmployeeID={payload.employee_id}, CycleID={payload.cycle_id}",
        ip_address=_client_ip(request),
    )
    return _to_out(performance)


@router.post("/{performance_id}/kpas", response_model=EmployeeKPAOut, status_code=status.HTTP_201_CREATED)
def add_kpa(
    performance_id: int, payload: EmployeeKPACreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_any_permission("ASSIGNMENT.EDIT", "ASSIGNMENT.PROPOSE")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_editable(performance)

    kpa = db.get(KPAMaster, payload.kpa_id)
    if kpa is None or not kpa.IsActive:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="KPA not found or inactive")

    existing = (
        db.query(EmployeeKPA)
        .filter(EmployeeKPA.PerformanceID == performance_id, EmployeeKPA.KPAID == payload.kpa_id)
        .one_or_none()
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This KPA is already assigned to this employee for this cycle")

    employee_kpa = EmployeeKPA(PerformanceID=performance_id, KPAID=payload.kpa_id, Weightage=0)
    db.add(employee_kpa)
    db.commit()
    db.refresh(employee_kpa)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="CREATE", module="KPA_KPI_ASSIGNMENT", record_id=str(employee_kpa.EmployeeKPAID),
        new_value=f"PerformanceID={performance_id}, KPAID={payload.kpa_id}", ip_address=_client_ip(request),
    )
    return _kpa_to_out(employee_kpa)


@router.delete("/{performance_id}/kpas/{employee_kpa_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_kpa(
    performance_id: int, employee_kpa_id: int, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_any_permission("ASSIGNMENT.EDIT", "ASSIGNMENT.PROPOSE")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_editable(performance)

    employee_kpa = db.get(EmployeeKPA, employee_kpa_id)
    if employee_kpa is None or employee_kpa.PerformanceID != performance_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="KPA assignment not found")

    db.delete(employee_kpa)
    db.commit()
    recompute_rollups(db, performance_id)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="DELETE", module="KPA_KPI_ASSIGNMENT", record_id=str(employee_kpa_id),
        old_value=f"PerformanceID={performance_id}, KPAID={employee_kpa.KPAID}", ip_address=_client_ip(request),
    )


@router.post(
    "/{performance_id}/kpas/{employee_kpa_id}/kpis", response_model=EmployeeKPIOut, status_code=status.HTTP_201_CREATED
)
def add_kpi(
    performance_id: int, employee_kpa_id: int, payload: EmployeeKPICreate, request: Request,
    db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_any_permission("ASSIGNMENT.EDIT", "ASSIGNMENT.PROPOSE")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_editable(performance)

    employee_kpa = db.get(EmployeeKPA, employee_kpa_id)
    if employee_kpa is None or employee_kpa.PerformanceID != performance_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="KPA assignment not found")

    kpi = db.get(KPIMaster, payload.kpi_id)
    if kpi is None or not kpi.IsActive:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="KPI not found or inactive")
    if kpi.KPAID != employee_kpa.KPAID:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="This KPI belongs to a different KPA in the master data and cannot be filed under this one",
        )

    validate_row_weightage(payload.weightage)
    validate_target(kpi.MeasurementType, payload.target)
    check_duplicate_kpi(db, performance_id, payload.kpi_id)

    employee_kpi = EmployeeKPI(
        EmployeeKPAID=employee_kpa_id, KPIID=payload.kpi_id, Description=payload.description,
        Target=payload.target, Unit=payload.unit or kpi.Unit, MeasurementType=kpi.MeasurementType,
        Weightage=payload.weightage, DueDate=payload.due_date, EvidenceRequired=payload.evidence_required,
    )
    db.add(employee_kpi)
    db.commit()
    db.refresh(employee_kpi)
    recompute_rollups(db, performance_id)
    db.refresh(employee_kpi)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="CREATE", module="KPA_KPI_ASSIGNMENT", record_id=str(employee_kpi.EmployeeKPIID),
        new_value=f"KPIID={payload.kpi_id}, Weightage={payload.weightage}, Target={payload.target}",
        ip_address=_client_ip(request),
    )
    return _kpi_to_out(employee_kpi)


@router.put("/{performance_id}/kpis/{employee_kpi_id}", response_model=EmployeeKPIOut)
def update_kpi(
    performance_id: int, employee_kpi_id: int, payload: EmployeeKPIUpdate, request: Request,
    db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_any_permission("ASSIGNMENT.EDIT", "ASSIGNMENT.PROPOSE")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_editable(performance)

    employee_kpi = db.get(EmployeeKPI, employee_kpi_id)
    if employee_kpi is None or employee_kpi.employee_kpa.PerformanceID != performance_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="KPI assignment not found")

    new_weightage = payload.weightage if payload.weightage is not None else employee_kpi.Weightage
    validate_row_weightage(new_weightage)
    new_target = payload.target if payload.target is not None else employee_kpi.Target
    validate_target(employee_kpi.MeasurementType, new_target)

    old_value = f"Weightage={employee_kpi.Weightage}, Target={employee_kpi.Target}"

    if payload.description is not None:
        employee_kpi.Description = payload.description
    if payload.target is not None:
        employee_kpi.Target = payload.target
    if payload.unit is not None:
        employee_kpi.Unit = payload.unit
    if payload.weightage is not None:
        employee_kpi.Weightage = payload.weightage
    if payload.due_date is not None:
        employee_kpi.DueDate = payload.due_date
    if payload.evidence_required is not None:
        employee_kpi.EvidenceRequired = payload.evidence_required

    db.commit()
    recompute_rollups(db, performance_id)
    db.refresh(employee_kpi)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="EDIT", module="KPA_KPI_ASSIGNMENT", record_id=str(employee_kpi_id),
        old_value=old_value, new_value=f"Weightage={employee_kpi.Weightage}, Target={employee_kpi.Target}",
        ip_address=_client_ip(request),
    )
    return _kpi_to_out(employee_kpi)


@router.delete("/{performance_id}/kpis/{employee_kpi_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_kpi(
    performance_id: int, employee_kpi_id: int, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_any_permission("ASSIGNMENT.EDIT", "ASSIGNMENT.PROPOSE")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_editable(performance)

    employee_kpi = db.get(EmployeeKPI, employee_kpi_id)
    if employee_kpi is None or employee_kpi.employee_kpa.PerformanceID != performance_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="KPI assignment not found")

    db.delete(employee_kpi)
    db.commit()
    recompute_rollups(db, performance_id)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="DELETE", module="KPA_KPI_ASSIGNMENT", record_id=str(employee_kpi_id),
        ip_address=_client_ip(request),
    )


@router.post("/{performance_id}/submit", response_model=AssignmentOut)
def submit_assignment(
    performance_id: int, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("ASSIGNMENT.EDIT")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_editable(performance)
    validate_submission_ready(performance)

    old_status = performance.Status
    performance.Status = KPI_ASSIGNED
    db.commit()
    db.refresh(performance)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="WORKFLOW_TRANSITION", module="KPA_KPI_ASSIGNMENT", record_id=str(performance_id),
        old_value=old_status, new_value=KPI_ASSIGNED, ip_address=_client_ip(request),
    )
    return _to_out(performance)


@router.get("/{performance_id}/export")
def export_assignment(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("ASSIGNMENT.VIEW")),
):
    """Stage-wise export for the KPI Assignment stage (spec Section 36A)."""
    performance = _get_scoped_performance(db, performance_id, ctx)
    rows = []
    for employee_kpa in performance.kpas:
        for kpi in employee_kpa.kpis:
            rows.append([
                employee_kpa.kpa.KPAName, kpi.kpi.KPIName, kpi.Description or "",
                kpi.Target if kpi.Target is not None else "", kpi.Unit or "", kpi.MeasurementType,
                kpi.Weightage, kpi.DueDate.isoformat() if kpi.DueDate else "",
                "Yes" if kpi.EvidenceRequired else "No",
            ])

    content = build_export_workbook(
        sheet_title="KPI Assignment",
        headers=["KPA", "KPI", "Description", "Target", "Unit", "Measurement Type", "Weightage", "Due Date", "Evidence Required"],
        rows=rows,
        generated_by=ctx.ad_username,
        context_label=f"KPI Assignment - {performance.employee.FullName} ({performance.cycle.CycleName})",
        filter_criteria=f"Stage=KPI_ASSIGNMENT, Status={performance.Status}",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=KPI_Assignment_{performance.employee.EmployeeCode}_{performance.cycle.CycleName}.xlsx"
        },
    )
