"""
Employee Master (spec Section 6). Unlike the org masters, view access here
is scoped by role per the RBAC matrix: an Employee sees only themself, a
Manager sees their direct reports, a HOD sees their department's employees;
HR/Plant Head/MD/HR Administrator see everyone. Scoping is enforced here in
the query, not just hidden in the UI (Section 33).
"""
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import CurrentContext, get_current_context, require_permission
from app.db.base import get_db
from app.models.employee import Employee
from app.schemas.employee import EmployeeCreate, EmployeeOut, EmployeeSelfUpdate, EmployeeUpdate
from app.schemas.masters import DeactivateRequest
from app.services import master_service as ms
from app.services.attachment_service import (
    delete_file,
    generate_stored_filename,
    image_content_type,
    read_file,
    sanitize_filename,
    save_file,
    validate_image_extension,
    validate_size,
    virus_scan_hook,
)
from app.services.audit_service import write_audit
from app.services.export_service import build_export_workbook
from app.services.profile_service import employee_photo_url

router = APIRouter(prefix="/employees", tags=["employees"])

BROAD_ACCESS_ROLES = {"HR", "HR_ADMIN", "PLANT_HEAD", "MD", "SYS_ADMIN"}


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _to_out(e: Employee) -> EmployeeOut:
    return EmployeeOut(
        employee_id=e.EmployeeID,
        employee_code=e.EmployeeCode,
        ad_username=e.ADUsername,
        full_name=e.FullName,
        email=e.Email,
        department_id=e.DepartmentID,
        department_name=e.department.DeptName if e.department else None,
        section_id=e.SectionID,
        section_name=e.section.SectionName if e.section else None,
        designation_id=e.DesignationID,
        designation_name=e.designation.DesignationName if e.designation else None,
        grade_id=e.GradeID,
        grade_name=e.grade.GradeName if e.grade else None,
        plant_id=e.PlantID,
        plant_name=e.plant.PlantName if e.plant else None,
        employee_category_id=e.EmployeeCategoryID,
        date_of_joining=e.DateOfJoining,
        manager_id=e.ManagerID,
        manager_name=e.manager.FullName if e.manager else None,
        hod_id=e.HODID,
        hod_name=e.hod.FullName if e.hod else None,
        hr_id=e.HRID,
        hr_name=e.hr_contact.FullName if e.hr_contact else None,
        employment_status=e.EmploymentStatus,
        is_active=e.IsActive,
        photo_url=employee_photo_url(e),
    )


def _apply_scope(query, ctx: CurrentContext, db: Session):
    """Restrict the query per Section 5's role-based visibility rules."""
    if BROAD_ACCESS_ROLES & set(ctx.role_codes):
        return query
    if "HOD" in ctx.role_codes:
        return query.filter(Employee.HODID == ctx.employee_id)
    if "MANAGER" in ctx.role_codes:
        return query.filter(Employee.ManagerID == ctx.employee_id)
    # Plain EMPLOYEE role: self only
    return query.filter(Employee.EmployeeID == ctx.employee_id)


@router.get("", response_model=list[EmployeeOut])
def list_employees(
    search: str | None = None,
    department_id: int | None = None,
    designation_id: int | None = None,
    grade_id: int | None = None,
    manager_id: int | None = None,
    hod_id: int | None = None,
    plant_id: int | None = None,
    employment_status: str | None = None,
    active_only: bool | None = None,
    db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("EMPLOYEE_MASTER.VIEW")),
):
    query = db.query(Employee)
    query = _apply_scope(query, ctx, db)

    if search:
        like = f"%{search}%"
        query = query.filter((Employee.FullName.ilike(like)) | (Employee.EmployeeCode.ilike(like)))
    if department_id is not None:
        query = query.filter(Employee.DepartmentID == department_id)
    if designation_id is not None:
        query = query.filter(Employee.DesignationID == designation_id)
    if grade_id is not None:
        query = query.filter(Employee.GradeID == grade_id)
    if manager_id is not None:
        query = query.filter(Employee.ManagerID == manager_id)
    if hod_id is not None:
        query = query.filter(Employee.HODID == hod_id)
    if plant_id is not None:
        query = query.filter(Employee.PlantID == plant_id)
    if employment_status is not None:
        query = query.filter(Employee.EmploymentStatus == employment_status)
    if active_only is not None:
        query = query.filter(Employee.IsActive == active_only)

    return [_to_out(e) for e in query.order_by(Employee.EmployeeCode).all()]


# NOTE: this literal-path route MUST be registered before GET /{employee_id}.
# The route path here is plain "/employees/{employee_id}" (no ":int" convertor),
# so Starlette matches on string patterns first and FastAPI validates the
# type afterward - "/employees/export" would otherwise match {employee_id}
# and fail type validation (422) before ever reaching this handler.
@router.get("/export")
def export_employees(
    department_id: int | None = None,
    db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("EMPLOYEE_MASTER.VIEW")),
):
    """Export respects the same role-based scope as the list endpoint - a
    Manager exporting gets only their own reports (spec Section 36A)."""
    query = _apply_scope(db.query(Employee), ctx, db)
    if department_id is not None:
        query = query.filter(Employee.DepartmentID == department_id)
    rows = query.order_by(Employee.EmployeeCode).all()

    content = build_export_workbook(
        sheet_title="Employees",
        headers=[
            "Employee Code", "AD Username", "Full Name", "Email", "Department", "Designation",
            "Grade", "Plant", "Date of Joining", "Manager", "HOD", "Employment Status", "Active",
        ],
        rows=[
            [
                e.EmployeeCode, e.ADUsername, e.FullName, e.Email or "",
                e.department.DeptName if e.department else "",
                e.designation.DesignationName if e.designation else "",
                e.grade.GradeName if e.grade else "",
                e.plant.PlantName if e.plant else "",
                e.DateOfJoining.isoformat() if e.DateOfJoining else "",
                e.manager.FullName if e.manager else "",
                e.hod.FullName if e.hod else "",
                e.EmploymentStatus, "Yes" if e.IsActive else "No",
            ]
            for e in rows
        ],
        generated_by=ctx.ad_username,
        context_label="Employee Master Export",
        filter_criteria=f"department_id={department_id}" if department_id else "None (scoped to your role)",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Employee_Master_Export.xlsx"},
    )


# NOTE: same literal-path-before-{employee_id} requirement as /export
# above - both "/me" routes MUST stay registered before GET /{employee_id}.
@router.get("/me", response_model=EmployeeOut)
def get_my_profile(
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(get_current_context),
):
    """Self-service profile view/edit (this user's own request: "add my
    profile page for all accounts where he or she can update his own
    profile details"). Available to every logged-in account regardless of
    role - unlike the rest of this module, no EMPLOYEE_MASTER.VIEW check,
    since seeing your own record is not an admin capability."""
    if ctx.employee_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This account has no linked employee record")
    employee = db.get(Employee, ctx.employee_id)
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Employee record not found")
    return _to_out(employee)


@router.put("/me", response_model=EmployeeOut)
def update_my_profile(
    payload: EmployeeSelfUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(get_current_context),
):
    """Deliberately narrow (see EmployeeSelfUpdate's docstring) - only
    contact info, not the structural/org fields that stay behind
    EMPLOYEE_MASTER.EDIT on PUT /employees/{id} (HR/Plant Head/MD/HR
    Admin - "HR and Plant head can update anyone profile")."""
    if ctx.employee_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This account has no linked employee record")
    employee = db.get(Employee, ctx.employee_id)
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Employee record not found")

    old_email = employee.Email
    if payload.email is not None:
        employee.Email = payload.email
    db.commit()
    db.refresh(employee)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="EDIT", module="EMPLOYEE_MASTER", record_id=str(employee.EmployeeID),
        old_value=f"Email={old_email}", new_value=f"Email={employee.Email}",
        reason="Self-service profile update", ip_address=_client_ip(request),
    )
    return _to_out(employee)


def _ensure_can_manage_photo(ctx: CurrentContext, employee_id: int) -> None:
    if ctx.employee_id == employee_id:
        return
    if "EMPLOYEE_MASTER.EDIT" in ctx.permission_codes:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You can only manage your own photo")


@router.post("/{employee_id}/photo", response_model=EmployeeOut)
def upload_employee_photo(
    employee_id: int, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(get_current_context),
):
    """Available to the employee themself (self-service - "add his or her
    own pic which display everywhere before name") or to anyone holding
    EMPLOYEE_MASTER.EDIT (HR/Plant Head/MD/HR Admin - "HR and Plant head
    can update anyone profile"), matching this file's existing
    EMPLOYEE_MASTER.EDIT-gated employee-editing routes rather than a new
    permission code."""
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Employee not found")
    _ensure_can_manage_photo(ctx, employee_id)

    safe_name = sanitize_filename(file.filename or "")
    validate_image_extension(safe_name)
    content = file.file.read()
    validate_size(len(content), get_settings().MAX_UPLOAD_SIZE_MB)
    virus_scan_hook(content)

    stored_filename = generate_stored_filename(safe_name)
    save_file(stored_filename, content)

    old_path = employee.ProfilePhotoPath
    employee.ProfilePhotoPath = stored_filename
    db.commit()
    db.refresh(employee)
    if old_path:
        delete_file(old_path)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="EDIT", module="EMPLOYEE_MASTER", record_id=str(employee_id),
        old_value="ProfilePhotoPath=<previous>" if old_path else "ProfilePhotoPath=<none>",
        new_value="ProfilePhotoPath=<updated>",
        reason="Profile photo updated", ip_address=_client_ip(request),
    )
    return _to_out(employee)


@router.delete("/{employee_id}/photo", response_model=EmployeeOut)
def remove_employee_photo(
    employee_id: int, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(get_current_context),
):
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Employee not found")
    _ensure_can_manage_photo(ctx, employee_id)

    old_path = employee.ProfilePhotoPath
    employee.ProfilePhotoPath = None
    db.commit()
    db.refresh(employee)
    if old_path:
        delete_file(old_path)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="EDIT", module="EMPLOYEE_MASTER", record_id=str(employee_id),
        reason="Profile photo removed", ip_address=_client_ip(request),
    )
    return _to_out(employee)


@router.get("/{employee_id}/photo")
def get_employee_photo(
    employee_id: int, db: Session = Depends(get_db), ctx: CurrentContext = Depends(get_current_context),
):
    """No EMPLOYEE_MASTER.VIEW scope check here on purpose: a photo is a
    display convenience, not sensitive master data, and it needs to render
    "everywhere before the name" (topbar, Employees list, Users & Roles,
    every stage of Reviews & Approvals) regardless of whether the viewer's
    role would normally see that specific employee's full record - any
    logged-in account can fetch any employee's photo, the same way an
    org's internal directory photo usually works."""
    employee = db.get(Employee, employee_id)
    if employee is None or not employee.ProfilePhotoPath:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No photo set for this employee")
    content = read_file(employee.ProfilePhotoPath)
    return Response(
        content=content,
        media_type=image_content_type(employee.ProfilePhotoPath),
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(
    employee_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("EMPLOYEE_MASTER.VIEW")),
):
    query = _apply_scope(db.query(Employee).filter(Employee.EmployeeID == employee_id), ctx, db)
    employee = query.one_or_none()
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Employee not found or outside your access scope")
    return _to_out(employee)


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: EmployeeCreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("EMPLOYEE_MASTER.EDIT")),
):
    if db.query(Employee).filter(Employee.EmployeeCode == payload.employee_code).one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Employee code already exists")
    if db.query(Employee).filter(Employee.ADUsername == payload.ad_username).one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="AD username is already mapped to an employee")

    employee = Employee(
        EmployeeCode=payload.employee_code,
        ADUsername=payload.ad_username,
        FullName=payload.full_name,
        Email=payload.email,
        DepartmentID=payload.department_id,
        SectionID=payload.section_id,
        DesignationID=payload.designation_id,
        GradeID=payload.grade_id,
        PlantID=payload.plant_id,
        EmployeeCategoryID=payload.employee_category_id,
        DateOfJoining=payload.date_of_joining,
        ManagerID=payload.manager_id,
        HODID=payload.hod_id,
        HRID=payload.hr_id,
        EmploymentStatus=payload.employment_status,
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    from app.services.audit_service import write_audit
    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="CREATE", module="EMPLOYEE_MASTER", record_id=str(employee.EmployeeID),
        new_value=f"EmployeeCode={payload.employee_code}, ADUsername={payload.ad_username}",
        ip_address=_client_ip(request),
    )
    return _to_out(employee)


@router.put("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: int, payload: EmployeeUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("EMPLOYEE_MASTER.EDIT")),
):
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Employee not found")

    update_fields = payload.model_dump(exclude={"reason"}, exclude_none=True)
    field_map = {
        "full_name": "FullName", "email": "Email", "department_id": "DepartmentID",
        "section_id": "SectionID", "designation_id": "DesignationID", "grade_id": "GradeID",
        "plant_id": "PlantID", "employee_category_id": "EmployeeCategoryID",
        "date_of_joining": "DateOfJoining", "manager_id": "ManagerID", "hod_id": "HODID",
        "hr_id": "HRID", "employment_status": "EmploymentStatus",
    }
    old_value = {field_map[k]: getattr(employee, field_map[k]) for k in update_fields}
    for key, value in update_fields.items():
        setattr(employee, field_map[key], value)

    db.commit()
    db.refresh(employee)

    from app.services.audit_service import write_audit
    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="EDIT", module="EMPLOYEE_MASTER", record_id=str(employee_id),
        old_value=str(old_value), new_value=str({field_map[k]: v for k, v in update_fields.items()}),
        reason=payload.reason, ip_address=_client_ip(request),
    )
    return _to_out(employee)


@router.post("/{employee_id}/deactivate", response_model=EmployeeOut)
def deactivate_employee(
    employee_id: int, payload: DeactivateRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("EMPLOYEE_MASTER.DEACTIVATE")),
):
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Employee not found")
    employee.IsActive = False
    employee.EmploymentStatus = "INACTIVE"
    db.commit()

    from app.services.audit_service import write_audit
    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="DEACTIVATE", module="EMPLOYEE_MASTER", record_id=str(employee_id),
        reason=payload.reason, ip_address=_client_ip(request),
    )
    return _to_out(employee)
