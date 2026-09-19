from datetime import date

from pydantic import BaseModel, Field


class EmployeeCreate(BaseModel):
    employee_code: str
    ad_username: str = Field(examples=["COMPANY\\jdoe"])
    full_name: str
    email: str | None = None
    department_id: int | None = None
    section_id: int | None = None
    designation_id: int | None = None
    grade_id: int | None = None
    plant_id: int | None = None
    employee_category_id: int | None = None
    date_of_joining: date | None = None
    manager_id: int | None = None
    hod_id: int | None = None
    hr_id: int | None = None
    employment_status: str = "ACTIVE"


class EmployeeSelfUpdate(BaseModel):
    """What an employee may change on their own record via PUT
    /employees/me - deliberately narrow (contact info only). Everything
    structural (department, designation, manager/HOD/HR mapping,
    employment status) stays behind EMPLOYEE_MASTER.EDIT (HR/Plant
    Head/MD/HR Admin) on the existing PUT /employees/{id} route - a
    self-service screen is not the place to let someone reassign their
    own department or manager."""
    email: str | None = None


class EmployeeUpdate(BaseModel):
    """All fields optional; `reason` is mandatory and goes to the audit trail."""
    full_name: str | None = None
    email: str | None = None
    department_id: int | None = None
    section_id: int | None = None
    designation_id: int | None = None
    grade_id: int | None = None
    plant_id: int | None = None
    employee_category_id: int | None = None
    date_of_joining: date | None = None
    manager_id: int | None = None
    hod_id: int | None = None
    hr_id: int | None = None
    employment_status: str | None = None
    reason: str


class EmployeeOut(BaseModel):
    employee_id: int
    employee_code: str
    ad_username: str
    full_name: str
    email: str | None
    department_id: int | None
    department_name: str | None
    section_id: int | None
    section_name: str | None
    designation_id: int | None
    designation_name: str | None
    grade_id: int | None
    grade_name: str | None
    plant_id: int | None
    plant_name: str | None
    employee_category_id: int | None
    date_of_joining: date | None
    manager_id: int | None
    manager_name: str | None
    hod_id: int | None
    hod_name: str | None
    hr_id: int | None
    hr_name: str | None
    employment_status: str
    is_active: bool
    photo_url: str | None = None
