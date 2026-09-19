from pydantic import BaseModel


class CompanyCreate(BaseModel):
    company_code: str
    company_name: str


class CompanyUpdate(BaseModel):
    company_name: str | None = None


class CompanyOut(BaseModel):
    company_id: int
    company_code: str
    company_name: str
    is_active: bool
    logo_url: str | None = None

    model_config = {"from_attributes": True}


class PlantCreate(BaseModel):
    company_id: int
    plant_code: str
    plant_name: str


class PlantUpdate(BaseModel):
    plant_name: str | None = None
    company_id: int | None = None


class PlantOut(BaseModel):
    plant_id: int
    company_id: int
    plant_code: str
    plant_name: str
    is_active: bool

    model_config = {"from_attributes": True}


class DepartmentCreate(BaseModel):
    plant_id: int
    dept_code: str
    dept_name: str


class DepartmentUpdate(BaseModel):
    dept_name: str | None = None
    plant_id: int | None = None


class DepartmentOut(BaseModel):
    department_id: int
    plant_id: int
    dept_code: str
    dept_name: str
    is_active: bool

    model_config = {"from_attributes": True}


class SectionCreate(BaseModel):
    department_id: int
    section_code: str
    section_name: str


class SectionUpdate(BaseModel):
    section_name: str | None = None
    department_id: int | None = None


class SectionOut(BaseModel):
    section_id: int
    department_id: int
    section_code: str
    section_name: str
    is_active: bool

    model_config = {"from_attributes": True}


class DesignationCreate(BaseModel):
    designation_code: str
    designation_name: str


class DesignationUpdate(BaseModel):
    designation_name: str | None = None


class DesignationOut(BaseModel):
    designation_id: int
    designation_code: str
    designation_name: str
    is_active: bool

    model_config = {"from_attributes": True}


class GradeCreate(BaseModel):
    grade_code: str
    grade_name: str


class GradeUpdate(BaseModel):
    grade_name: str | None = None


class GradeOut(BaseModel):
    grade_id: int
    grade_code: str
    grade_name: str
    is_active: bool

    model_config = {"from_attributes": True}


class EmployeeCategoryCreate(BaseModel):
    category_code: str
    category_name: str


class EmployeeCategoryUpdate(BaseModel):
    category_name: str | None = None


class EmployeeCategoryOut(BaseModel):
    employee_category_id: int
    category_code: str
    category_name: str
    is_active: bool

    model_config = {"from_attributes": True}


class DeactivateRequest(BaseModel):
    reason: str


class ActivateRequest(BaseModel):
    reason: str
