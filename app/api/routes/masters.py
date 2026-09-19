"""
Org master endpoints (spec Section 6). Every entity gets the same
Add/Edit/View/Activate/Deactivate/Search/Export surface via the generic
master_service; only parent-existence checks differ per entity.
"""
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import CurrentContext, get_current_context, require_permission
from app.db.base import get_db
from app.models.masters import Company, Department, Designation, EmployeeCategory, Grade, Plant, Section
from app.schemas.masters import (
    ActivateRequest,
    CompanyCreate,
    CompanyOut,
    CompanyUpdate,
    DeactivateRequest,
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    DesignationCreate,
    DesignationOut,
    DesignationUpdate,
    EmployeeCategoryCreate,
    EmployeeCategoryOut,
    EmployeeCategoryUpdate,
    GradeCreate,
    GradeOut,
    GradeUpdate,
    PlantCreate,
    PlantOut,
    PlantUpdate,
    SectionCreate,
    SectionOut,
    SectionUpdate,
)
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
from app.services.profile_service import company_logo_url

router = APIRouter(prefix="/masters", tags=["masters"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# master_service's generic list_records/create_record/update_record/
# set_active_status all return raw ORM instances (PascalCase attributes)
# rather than translating to the snake_case *Out schemas - that raw
# contract is relied on by every export_* endpoint below (direct
# r.CompanyCode-style attribute access), so it can't change. Instead each
# entity gets its own tiny _to_out() translator, applied only at the
# JSON-response call sites, mirroring the _to_out() pattern already used
# elsewhere in this codebase (e.g. kpa.py/kpi.py).
def _company_out(r: Company) -> CompanyOut:
    return CompanyOut(
        company_id=r.CompanyID, company_code=r.CompanyCode, company_name=r.CompanyName, is_active=r.IsActive,
        logo_url=company_logo_url(r),
    )


def _plant_out(r: Plant) -> PlantOut:
    return PlantOut(
        plant_id=r.PlantID, company_id=r.CompanyID, plant_code=r.PlantCode, plant_name=r.PlantName,
        is_active=r.IsActive,
    )


def _department_out(r: Department) -> DepartmentOut:
    return DepartmentOut(
        department_id=r.DepartmentID, plant_id=r.PlantID, dept_code=r.DeptCode, dept_name=r.DeptName,
        is_active=r.IsActive,
    )


def _section_out(r: Section) -> SectionOut:
    return SectionOut(
        section_id=r.SectionID, department_id=r.DepartmentID, section_code=r.SectionCode,
        section_name=r.SectionName, is_active=r.IsActive,
    )


def _designation_out(r: Designation) -> DesignationOut:
    return DesignationOut(
        designation_id=r.DesignationID, designation_code=r.DesignationCode,
        designation_name=r.DesignationName, is_active=r.IsActive,
    )


def _grade_out(r: Grade) -> GradeOut:
    return GradeOut(grade_id=r.GradeID, grade_code=r.GradeCode, grade_name=r.GradeName, is_active=r.IsActive)


def _employee_category_out(r: EmployeeCategory) -> EmployeeCategoryOut:
    return EmployeeCategoryOut(
        employee_category_id=r.EmployeeCategoryID, category_code=r.CategoryCode, category_name=r.CategoryName,
        is_active=r.IsActive,
    )


# ===================================================================== Company
COMPANY_CFG = ms.MasterFieldConfig(Company, "CompanyID", "CompanyCode", "CompanyName", "MASTERS.COMPANY")


@router.get("/companies", response_model=list[CompanyOut])
def list_companies(
    search: str | None = None,
    active_only: bool | None = None,
    db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW")),
):
    return [_company_out(r) for r in ms.list_records(db, COMPANY_CFG, search, active_only)]


@router.post("/companies", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    data = {"CompanyCode": payload.company_code, "CompanyName": payload.company_name}
    return _company_out(ms.create_record(db, COMPANY_CFG, data, ctx, _client_ip(request)))


@router.put("/companies/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: int, payload: CompanyUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    data = {k: v for k, v in {"CompanyName": payload.company_name}.items() if v is not None}
    return _company_out(ms.update_record(db, COMPANY_CFG, company_id, data, ctx, _client_ip(request)))


@router.post("/companies/{company_id}/deactivate", response_model=CompanyOut)
def deactivate_company(
    company_id: int, payload: DeactivateRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    return _company_out(
        ms.set_active_status(db, COMPANY_CFG, company_id, False, payload.reason, ctx, _client_ip(request))
    )


@router.post("/companies/{company_id}/activate", response_model=CompanyOut)
def activate_company(
    company_id: int, payload: ActivateRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    return _company_out(
        ms.set_active_status(db, COMPANY_CFG, company_id, True, payload.reason, ctx, _client_ip(request))
    )


@router.post("/companies/{company_id}/logo", response_model=CompanyOut)
def upload_company_logo(
    company_id: int, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    """Company logo upload - "provision to add company logo by HR or
    plant head". Gated by the same MASTERS.EDIT permission as every other
    master-data edit in this file, which sql/005 grants to HR, Plant
    Head, MD and HR Administrator (the same four roles that can already
    rename a Company here) - not a new permission code."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Company not found")

    safe_name = sanitize_filename(file.filename or "")
    validate_image_extension(safe_name)
    content = file.file.read()
    validate_size(len(content), get_settings().MAX_UPLOAD_SIZE_MB)
    virus_scan_hook(content)

    stored_filename = generate_stored_filename(safe_name)
    save_file(stored_filename, content)

    old_path = company.LogoPath
    company.LogoPath = stored_filename
    db.commit()
    db.refresh(company)
    if old_path:
        delete_file(old_path)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="EDIT", module="MASTERS", record_id=str(company_id),
        old_value="LogoPath=<previous>" if old_path else "LogoPath=<none>", new_value="LogoPath=<updated>",
        reason="Company logo updated", ip_address=_client_ip(request),
    )
    return _company_out(company)


@router.delete("/companies/{company_id}/logo", response_model=CompanyOut)
def remove_company_logo(
    company_id: int, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Company not found")

    old_path = company.LogoPath
    company.LogoPath = None
    db.commit()
    db.refresh(company)
    if old_path:
        delete_file(old_path)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="EDIT", module="MASTERS", record_id=str(company_id),
        reason="Company logo removed", ip_address=_client_ip(request),
    )
    return _company_out(company)


@router.get("/companies/{company_id}/logo")
def get_company_logo(
    company_id: int, db: Session = Depends(get_db), ctx: CurrentContext = Depends(get_current_context),
):
    """No MASTERS.VIEW check on purpose, matching Employee photo's
    GET /employees/{id}/photo: a logo is branding, needed in the sidebar
    for every logged-in account, not gated master-data detail."""
    company = db.get(Company, company_id)
    if company is None or not company.LogoPath:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No logo set for this company")
    content = read_file(company.LogoPath)
    return Response(
        content=content, media_type=image_content_type(company.LogoPath),
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/companies/export")
def export_companies(db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW"))):
    rows = ms.list_records(db, COMPANY_CFG)
    content = build_export_workbook(
        sheet_title="Companies",
        headers=["Company Code", "Company Name", "Active"],
        rows=[[r.CompanyCode, r.CompanyName, "Yes" if r.IsActive else "No"] for r in rows],
        generated_by=ctx.ad_username,
        context_label="Master Export - Companies",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Companies_Master.xlsx"},
    )


# ===================================================================== Plant
PLANT_CFG = ms.MasterFieldConfig(Plant, "PlantID", "PlantCode", "PlantName", "MASTERS.PLANT")


@router.get("/plants", response_model=list[PlantOut])
def list_plants(
    search: str | None = None, active_only: bool | None = None, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW")),
):
    return [_plant_out(r) for r in ms.list_records(db, PLANT_CFG, search, active_only)]


@router.post("/plants", response_model=PlantOut, status_code=status.HTTP_201_CREATED)
def create_plant(
    payload: PlantCreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    if db.get(Company, payload.company_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Company not found")
    data = {"CompanyID": payload.company_id, "PlantCode": payload.plant_code, "PlantName": payload.plant_name}
    return _plant_out(ms.create_record(db, PLANT_CFG, data, ctx, _client_ip(request)))


@router.put("/plants/{plant_id}", response_model=PlantOut)
def update_plant(
    plant_id: int, payload: PlantUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    if payload.company_id is not None and db.get(Company, payload.company_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Company not found")
    data = {
        k: v for k, v in {"PlantName": payload.plant_name, "CompanyID": payload.company_id}.items()
        if v is not None
    }
    return _plant_out(ms.update_record(db, PLANT_CFG, plant_id, data, ctx, _client_ip(request)))


@router.post("/plants/{plant_id}/deactivate", response_model=PlantOut)
def deactivate_plant(
    plant_id: int, payload: DeactivateRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    return _plant_out(
        ms.set_active_status(db, PLANT_CFG, plant_id, False, payload.reason, ctx, _client_ip(request))
    )


@router.post("/plants/{plant_id}/activate", response_model=PlantOut)
def activate_plant(
    plant_id: int, payload: ActivateRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    return _plant_out(
        ms.set_active_status(db, PLANT_CFG, plant_id, True, payload.reason, ctx, _client_ip(request))
    )


@router.get("/plants/export")
def export_plants(db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW"))):
    rows = ms.list_records(db, PLANT_CFG)
    content = build_export_workbook(
        sheet_title="Plants",
        headers=["Plant Code", "Plant Name", "Company ID", "Active"],
        rows=[[r.PlantCode, r.PlantName, r.CompanyID, "Yes" if r.IsActive else "No"] for r in rows],
        generated_by=ctx.ad_username,
        context_label="Master Export - Plants",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Plants_Master.xlsx"},
    )


# ================================================================== Department
DEPARTMENT_CFG = ms.MasterFieldConfig(Department, "DepartmentID", "DeptCode", "DeptName", "MASTERS.DEPARTMENT")


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(
    search: str | None = None, active_only: bool | None = None, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW")),
):
    return [_department_out(r) for r in ms.list_records(db, DEPARTMENT_CFG, search, active_only)]


@router.post("/departments", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
def create_department(
    payload: DepartmentCreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    if db.get(Plant, payload.plant_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Plant not found")
    data = {"PlantID": payload.plant_id, "DeptCode": payload.dept_code, "DeptName": payload.dept_name}
    return _department_out(ms.create_record(db, DEPARTMENT_CFG, data, ctx, _client_ip(request)))


@router.put("/departments/{department_id}", response_model=DepartmentOut)
def update_department(
    department_id: int, payload: DepartmentUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    if payload.plant_id is not None and db.get(Plant, payload.plant_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Plant not found")
    data = {
        k: v for k, v in {"DeptName": payload.dept_name, "PlantID": payload.plant_id}.items() if v is not None
    }
    return _department_out(ms.update_record(db, DEPARTMENT_CFG, department_id, data, ctx, _client_ip(request)))


@router.post("/departments/{department_id}/deactivate", response_model=DepartmentOut)
def deactivate_department(
    department_id: int, payload: DeactivateRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    return _department_out(
        ms.set_active_status(db, DEPARTMENT_CFG, department_id, False, payload.reason, ctx, _client_ip(request))
    )


@router.post("/departments/{department_id}/activate", response_model=DepartmentOut)
def activate_department(
    department_id: int, payload: ActivateRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    return _department_out(
        ms.set_active_status(db, DEPARTMENT_CFG, department_id, True, payload.reason, ctx, _client_ip(request))
    )


@router.get("/departments/export")
def export_departments(
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW"))
):
    rows = ms.list_records(db, DEPARTMENT_CFG)
    content = build_export_workbook(
        sheet_title="Departments",
        headers=["Dept Code", "Dept Name", "Plant ID", "Active"],
        rows=[[r.DeptCode, r.DeptName, r.PlantID, "Yes" if r.IsActive else "No"] for r in rows],
        generated_by=ctx.ad_username,
        context_label="Master Export - Departments",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Departments_Master.xlsx"},
    )


# ===================================================================== Section
SECTION_CFG = ms.MasterFieldConfig(Section, "SectionID", "SectionCode", "SectionName", "MASTERS.SECTION")


@router.get("/sections", response_model=list[SectionOut])
def list_sections(
    search: str | None = None, active_only: bool | None = None, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW")),
):
    return [_section_out(r) for r in ms.list_records(db, SECTION_CFG, search, active_only)]


@router.post("/sections", response_model=SectionOut, status_code=status.HTTP_201_CREATED)
def create_section(
    payload: SectionCreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    if db.get(Department, payload.department_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Department not found")
    data = {
        "DepartmentID": payload.department_id, "SectionCode": payload.section_code,
        "SectionName": payload.section_name,
    }
    return _section_out(ms.create_record(db, SECTION_CFG, data, ctx, _client_ip(request)))


@router.put("/sections/{section_id}", response_model=SectionOut)
def update_section(
    section_id: int, payload: SectionUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    if payload.department_id is not None and db.get(Department, payload.department_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Department not found")
    data = {
        k: v for k, v in {"SectionName": payload.section_name, "DepartmentID": payload.department_id}.items()
        if v is not None
    }
    return _section_out(ms.update_record(db, SECTION_CFG, section_id, data, ctx, _client_ip(request)))


@router.post("/sections/{section_id}/deactivate", response_model=SectionOut)
def deactivate_section(
    section_id: int, payload: DeactivateRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    return _section_out(
        ms.set_active_status(db, SECTION_CFG, section_id, False, payload.reason, ctx, _client_ip(request))
    )


@router.post("/sections/{section_id}/activate", response_model=SectionOut)
def activate_section(
    section_id: int, payload: ActivateRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    return _section_out(
        ms.set_active_status(db, SECTION_CFG, section_id, True, payload.reason, ctx, _client_ip(request))
    )


@router.get("/sections/export")
def export_sections(db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW"))):
    rows = ms.list_records(db, SECTION_CFG)
    content = build_export_workbook(
        sheet_title="Sections",
        headers=["Section Code", "Section Name", "Department ID", "Active"],
        rows=[[r.SectionCode, r.SectionName, r.DepartmentID, "Yes" if r.IsActive else "No"] for r in rows],
        generated_by=ctx.ad_username,
        context_label="Master Export - Sections",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Sections_Master.xlsx"},
    )


# ================================================================= Designation
DESIGNATION_CFG = ms.MasterFieldConfig(
    Designation, "DesignationID", "DesignationCode", "DesignationName", "MASTERS.DESIGNATION"
)


@router.get("/designations", response_model=list[DesignationOut])
def list_designations(
    search: str | None = None, active_only: bool | None = None, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW")),
):
    return [_designation_out(r) for r in ms.list_records(db, DESIGNATION_CFG, search, active_only)]


@router.post("/designations", response_model=DesignationOut, status_code=status.HTTP_201_CREATED)
def create_designation(
    payload: DesignationCreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    data = {"DesignationCode": payload.designation_code, "DesignationName": payload.designation_name}
    return _designation_out(ms.create_record(db, DESIGNATION_CFG, data, ctx, _client_ip(request)))


@router.put("/designations/{designation_id}", response_model=DesignationOut)
def update_designation(
    designation_id: int, payload: DesignationUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    data = {k: v for k, v in {"DesignationName": payload.designation_name}.items() if v is not None}
    return _designation_out(ms.update_record(db, DESIGNATION_CFG, designation_id, data, ctx, _client_ip(request)))


@router.post("/designations/{designation_id}/deactivate", response_model=DesignationOut)
def deactivate_designation(
    designation_id: int, payload: DeactivateRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    return _designation_out(
        ms.set_active_status(db, DESIGNATION_CFG, designation_id, False, payload.reason, ctx, _client_ip(request))
    )


@router.post("/designations/{designation_id}/activate", response_model=DesignationOut)
def activate_designation(
    designation_id: int, payload: ActivateRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    return _designation_out(
        ms.set_active_status(db, DESIGNATION_CFG, designation_id, True, payload.reason, ctx, _client_ip(request))
    )


@router.get("/designations/export")
def export_designations(
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW"))
):
    rows = ms.list_records(db, DESIGNATION_CFG)
    content = build_export_workbook(
        sheet_title="Designations",
        headers=["Designation Code", "Designation Name", "Active"],
        rows=[[r.DesignationCode, r.DesignationName, "Yes" if r.IsActive else "No"] for r in rows],
        generated_by=ctx.ad_username,
        context_label="Master Export - Designations",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Designations_Master.xlsx"},
    )


# ======================================================================= Grade
GRADE_CFG = ms.MasterFieldConfig(Grade, "GradeID", "GradeCode", "GradeName", "MASTERS.GRADE")


@router.get("/grades", response_model=list[GradeOut])
def list_grades(
    search: str | None = None, active_only: bool | None = None, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW")),
):
    return [_grade_out(r) for r in ms.list_records(db, GRADE_CFG, search, active_only)]


@router.post("/grades", response_model=GradeOut, status_code=status.HTTP_201_CREATED)
def create_grade(
    payload: GradeCreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    data = {"GradeCode": payload.grade_code, "GradeName": payload.grade_name}
    return _grade_out(ms.create_record(db, GRADE_CFG, data, ctx, _client_ip(request)))


@router.put("/grades/{grade_id}", response_model=GradeOut)
def update_grade(
    grade_id: int, payload: GradeUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    data = {k: v for k, v in {"GradeName": payload.grade_name}.items() if v is not None}
    return _grade_out(ms.update_record(db, GRADE_CFG, grade_id, data, ctx, _client_ip(request)))


@router.post("/grades/{grade_id}/deactivate", response_model=GradeOut)
def deactivate_grade(
    grade_id: int, payload: DeactivateRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    return _grade_out(
        ms.set_active_status(db, GRADE_CFG, grade_id, False, payload.reason, ctx, _client_ip(request))
    )


@router.post("/grades/{grade_id}/activate", response_model=GradeOut)
def activate_grade(
    grade_id: int, payload: ActivateRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    return _grade_out(
        ms.set_active_status(db, GRADE_CFG, grade_id, True, payload.reason, ctx, _client_ip(request))
    )


@router.get("/grades/export")
def export_grades(db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW"))):
    rows = ms.list_records(db, GRADE_CFG)
    content = build_export_workbook(
        sheet_title="Grades",
        headers=["Grade Code", "Grade Name", "Active"],
        rows=[[r.GradeCode, r.GradeName, "Yes" if r.IsActive else "No"] for r in rows],
        generated_by=ctx.ad_username,
        context_label="Master Export - Grades",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Grades_Master.xlsx"},
    )


# =========================================================== Employee Category
CATEGORY_CFG = ms.MasterFieldConfig(
    EmployeeCategory, "EmployeeCategoryID", "CategoryCode", "CategoryName", "MASTERS.EMPLOYEE_CATEGORY"
)


@router.get("/employee-categories", response_model=list[EmployeeCategoryOut])
def list_employee_categories(
    search: str | None = None, active_only: bool | None = None, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW")),
):
    return [_employee_category_out(r) for r in ms.list_records(db, CATEGORY_CFG, search, active_only)]


@router.post("/employee-categories", response_model=EmployeeCategoryOut, status_code=status.HTTP_201_CREATED)
def create_employee_category(
    payload: EmployeeCategoryCreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    data = {"CategoryCode": payload.category_code, "CategoryName": payload.category_name}
    return _employee_category_out(ms.create_record(db, CATEGORY_CFG, data, ctx, _client_ip(request)))


@router.put("/employee-categories/{category_id}", response_model=EmployeeCategoryOut)
def update_employee_category(
    category_id: int, payload: EmployeeCategoryUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    data = {k: v for k, v in {"CategoryName": payload.category_name}.items() if v is not None}
    return _employee_category_out(ms.update_record(db, CATEGORY_CFG, category_id, data, ctx, _client_ip(request)))


@router.post("/employee-categories/{category_id}/deactivate", response_model=EmployeeCategoryOut)
def deactivate_employee_category(
    category_id: int, payload: DeactivateRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    return _employee_category_out(
        ms.set_active_status(db, CATEGORY_CFG, category_id, False, payload.reason, ctx, _client_ip(request))
    )


@router.post("/employee-categories/{category_id}/activate", response_model=EmployeeCategoryOut)
def activate_employee_category(
    category_id: int, payload: ActivateRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    return _employee_category_out(
        ms.set_active_status(db, CATEGORY_CFG, category_id, True, payload.reason, ctx, _client_ip(request))
    )


@router.get("/employee-categories/export")
def export_employee_categories(
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW"))
):
    rows = ms.list_records(db, CATEGORY_CFG)
    content = build_export_workbook(
        sheet_title="Employee Categories",
        headers=["Category Code", "Category Name", "Active"],
        rows=[[r.CategoryCode, r.CategoryName, "Yes" if r.IsActive else "No"] for r in rows],
        generated_by=ctx.ad_username,
        context_label="Master Export - Employee Categories",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=EmployeeCategories_Master.xlsx"},
    )
