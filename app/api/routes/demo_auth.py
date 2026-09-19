"""
Password management for local (non-AD) accounts - see demo_auth_service.
py's docstring for the two AUTH_MODE values that use this: demo_local
(the Windows 11 Home / no-AD local demo deployment) and hybrid (AD +
local users side by side, permitted in production).

demo_local is refused outright when ENVIRONMENT is production, the same
guard app/api/routes/auth.py applies at login - belt and braces, since a
demo-only password-reset endpoint reachable in production would itself
be a real vulnerability regardless of whether anyone can currently log
in with demo_local. hybrid has no such refusal: setting a local
account's password there is exactly the intended, production-safe
workflow for creating that account in the first place (see
DEPLOYMENT.md's "Hybrid (AD + local users)" section) - the same
HR_ADMIN/SYS_ADMIN/HR/PLANT_HEAD gate below is what keeps it safe, not
an environment check.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import CurrentContext, get_current_context, require_any_role
from app.db.base import get_db
from app.models.rbac import User
from app.schemas.demo_auth import DemoChangePasswordRequest, DemoSetPasswordRequest
from app.services.ad_service import ADAuthError
from app.services.audit_service import write_audit
from app.services.demo_auth_service import change_own_password, set_password

router = APIRouter(prefix="/auth/demo", tags=["auth-demo"])


def _ensure_demo_mode_enabled():
    settings = get_settings()
    if settings.AUTH_MODE not in ("demo_local", "hybrid"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Local password management requires AUTH_MODE=demo_local or AUTH_MODE=hybrid",
        )
    if settings.AUTH_MODE == "demo_local" and settings.ENVIRONMENT == "production":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="AUTH_MODE=demo_local is not permitted when ENVIRONMENT=production - use AUTH_MODE=hybrid instead",
        )


@router.post("/set-password/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_set_demo_password(
    user_id: int, payload: DemoSetPasswordRequest, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_any_role("HR_ADMIN", "SYS_ADMIN", "HR", "PLANT_HEAD")),
):
    _ensure_demo_mode_enabled()
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        set_password(db, user_id, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id, action="EDIT",
        module="DEMO_LOGIN", record_id=str(user_id), reason="Admin reset demo password",
    )


@router.put("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def self_change_demo_password(
    payload: DemoChangePasswordRequest, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(get_current_context),
):
    _ensure_demo_mode_enabled()
    try:
        change_own_password(db, ctx.user_id, payload.current_password, payload.new_password)
    except ADAuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id, action="EDIT",
        module="DEMO_LOGIN", record_id=str(ctx.user_id), reason="Self-service password change",
    )
