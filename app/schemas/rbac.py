from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Only used in AUTH_MODE=ldap_bind. In iis_forwarded mode /auth/login
    needs no body - identity comes from the forwarded header."""
    username: str = Field(examples=["COMPANY\\jdoe"])
    password: str


class CurrentUserResponse(BaseModel):
    ad_username: str
    employee_id: int | None
    employee_name: str | None
    role_codes: list[str]
    dashboard_route: str
    photo_url: str | None = None
    company_logo_url: str | None = None


class RoleOut(BaseModel):
    role_id: int
    role_code: str
    role_name: str
    is_business_role: bool
    is_active: bool

    model_config = {"from_attributes": True}


class PermissionOut(BaseModel):
    permission_id: int
    permission_code: str
    module: str
    description: str | None

    model_config = {"from_attributes": True}


class AssignRolePermissionsRequest(BaseModel):
    permission_codes: list[str]


class UserAdminCreate(BaseModel):
    """Fields for the AD-mapping admin screen (spec Section 5)."""
    ad_username: str = Field(examples=["COMPANY\\jdoe"])
    employee_id: int | None = None
    role_codes: list[str]
    is_active: bool = True


class UserAdminUpdate(BaseModel):
    employee_id: int | None = None
    role_codes: list[str] | None = None
    is_active: bool | None = None
    reason: str = Field(description="Required - recorded in the audit trail for this change")


class UserAdminOut(BaseModel):
    user_id: int
    ad_username: str
    employee_id: int | None
    employee_name: str | None
    employee_photo_url: str | None = None
    role_codes: list[str]
    is_active: bool

    model_config = {"from_attributes": True}
