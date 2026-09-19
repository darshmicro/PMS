from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import CurrentContext, get_current_context
from app.core.session import SESSION_COOKIE_NAME, create_session_token, session_cookie_kwargs
from app.db.base import get_db
from app.schemas.rbac import CurrentUserResponse, LoginRequest
from app.services import ad_service, demo_auth_service
from app.services.audit_service import write_audit
from app.services.auth_service import LoginError, default_dashboard_route, resolve_user_context

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=CurrentUserResponse)
def login(request: Request, response: Response, db: Session = Depends(get_db), body: LoginRequest | None = None):
    """
    AUTH_MODE=iis_forwarded: no body needed - IIS has already authenticated the
    user and forwarded their identity in a header. AUTH_MODE=ldap_bind: body
    with DOMAIN\\username + password is required and validated against AD.
    AUTH_MODE=demo_local: body with username + password is validated against
    the app's own Demo_Login table - a local-demo-only path (see
    demo_auth_service.py's docstring) that is refused outright whenever
    ENVIRONMENT=production, regardless of what AUTH_MODE is set to.
    AUTH_MODE=hybrid: body with username + password, checked against the
    local Demo_Login table FIRST (find_local_login) and, only if nothing
    local matches, against AD via the same ldap_bind path - one login
    screen serving both real AD users and local-only accounts (see
    demo_auth_service.py's docstring and DEPLOYMENT.md's "Hybrid (AD +
    local users)" section). Unlike demo_local, this IS permitted in
    production - AD users still get AD's own protections, and a local
    account is an explicit, individually-created exception (created via
    POST /admin/users + POST /auth/demo/set-password/{user_id}), not the
    only way in.
    """
    try:
        if settings.AUTH_MODE == "iis_forwarded":
            header_value = request.headers.get(settings.IIS_FORWARDED_USER_HEADER)
            ad_user_info = ad_service.authenticate_via_iis_header(header_value)
            resolved_username = ad_user_info.ad_username
        elif settings.AUTH_MODE == "ldap_bind":
            if body is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Username and password are required")
            ad_user_info = ad_service.authenticate_via_ldap_bind(body.username, body.password)
            resolved_username = ad_user_info.ad_username
        elif settings.AUTH_MODE == "demo_local":
            if settings.ENVIRONMENT == "production":
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="AUTH_MODE=demo_local is not permitted when ENVIRONMENT=production",
                )
            if body is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Username and password are required")
            resolved_username = demo_auth_service.authenticate_demo_login(db, body.username, body.password)
        elif settings.AUTH_MODE == "hybrid":
            if body is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Username and password are required")
            local_user = demo_auth_service.find_local_login(db, body.username)
            if local_user is not None:
                resolved_username = demo_auth_service.authenticate_demo_login(db, local_user.ADUsername, body.password)
            else:
                ad_user_info = ad_service.authenticate_via_ldap_bind(body.username, body.password)
                resolved_username = ad_user_info.ad_username
        else:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid AUTH_MODE configuration")
    except ad_service.ADAuthError:
        # Deliberately generic - never reveal whether the username exists (Sec 45)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    try:
        ctx = resolve_user_context(db, resolved_username)
    except LoginError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc))

    token = create_session_token(ctx.user_id)
    response.set_cookie(SESSION_COOKIE_NAME, token, **session_cookie_kwargs())

    write_audit(
        db,
        user_id=ctx.user_id,
        ad_username=ctx.ad_username,
        employee_id=ctx.employee_id,
        action="LOGIN",
        module="AUTH",
        ip_address=request.client.host if request.client else None,
    )

    return CurrentUserResponse(
        ad_username=ctx.ad_username,
        employee_id=ctx.employee_id,
        employee_name=ctx.employee_name,
        role_codes=ctx.role_codes,
        dashboard_route=default_dashboard_route(ctx.role_codes),
        photo_url=ctx.photo_url,
        company_logo_url=ctx.company_logo_url,
    )


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db), ctx: CurrentContext = Depends(get_current_context)):
    write_audit(
        db,
        user_id=ctx.user_id,
        ad_username=ctx.ad_username,
        employee_id=ctx.employee_id,
        action="LOGOUT",
        module="AUTH",
        ip_address=request.client.host if request.client else None,
    )
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"detail": "Logged out"}


@router.get("/me", response_model=CurrentUserResponse)
def me(db: Session = Depends(get_db), ctx: CurrentContext = Depends(get_current_context)):
    from app.models.employee import Employee
    from app.services.profile_service import company_logo_url, employee_photo_url

    employee_name = None
    photo_url = None
    logo_url = None
    if ctx.employee_id is not None:
        emp = db.get(Employee, ctx.employee_id)
        employee_name = emp.FullName if emp else None
        photo_url = employee_photo_url(emp)
        logo_url = company_logo_url(emp.plant.company) if emp and emp.plant else None

    return CurrentUserResponse(
        ad_username=ctx.ad_username,
        employee_id=ctx.employee_id,
        employee_name=employee_name,
        role_codes=ctx.role_codes,
        dashboard_route=default_dashboard_route(ctx.role_codes),
        photo_url=photo_url,
        company_logo_url=logo_url,
    )
