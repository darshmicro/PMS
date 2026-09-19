"""
System Configuration endpoints (spec Section 5 row 545 / M28). The final
row in the whole RBAC matrix: System Administrator only,
Create/View/Edit, no other role gets anything at all - so every endpoint
here is gated by require_any_role("SYS_ADMIN") rather than a permission
code shared with any other role, matching this module's own uniquely
narrow reach.

Every write is audited (write_audit) - this is app-wide operational
configuration, and Section 32's "every module's writes go through
Audit_Log" applies here as much as anywhere, arguably more so given what
this screen controls (SMTP relay, AD server address, file storage path).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_any_role
from app.db.base import get_db
from app.schemas.system_config import SystemConfigOut, SystemConfigUpsertIn
from app.services.audit_service import write_audit
from app.services.system_config_service import ConfigKeyRejected, get_config, list_config, upsert_config

router = APIRouter(prefix="/system-config", tags=["system-config"])


def _to_out(row) -> SystemConfigOut:
    return SystemConfigOut(
        config_id=row.ConfigID, config_key=row.ConfigKey, config_value=row.ConfigValue,
        description=row.Description, modified_by=row.ModifiedBy, modified_at=row.ModifiedAt,
    )


@router.get("", response_model=list[SystemConfigOut])
def list_system_config(
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_any_role("SYS_ADMIN")),
):
    return [_to_out(r) for r in list_config(db)]


@router.get("/{config_key}", response_model=SystemConfigOut)
def get_system_config(
    config_key: str, db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_any_role("SYS_ADMIN")),
):
    row = get_config(db, config_key)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Config key not found")
    return _to_out(row)


@router.post("/{config_key}", response_model=SystemConfigOut, status_code=status.HTTP_201_CREATED)
def create_system_config(
    config_key: str, payload: SystemConfigUpsertIn, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_any_role("SYS_ADMIN")),
):
    if get_config(db, config_key) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Config key already exists - use PUT to edit it")
    try:
        row = upsert_config(
            db, key=config_key, value=payload.config_value, description=payload.description,
            modified_by=ctx.user_id,
        )
    except ConfigKeyRejected as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id, action="CREATE",
        module="SYSTEM_CONFIG", record_id=config_key, new_value=payload.config_value,
        ip_address=request.client.host if request.client else None,
    )
    return _to_out(row)


@router.put("/{config_key}", response_model=SystemConfigOut)
def update_system_config(
    config_key: str, payload: SystemConfigUpsertIn, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_any_role("SYS_ADMIN")),
):
    existing = get_config(db, config_key)
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Config key not found - use POST to create it")
    old_value = existing.ConfigValue
    try:
        row = upsert_config(
            db, key=config_key, value=payload.config_value, description=payload.description,
            modified_by=ctx.user_id,
        )
    except ConfigKeyRejected as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id, action="EDIT",
        module="SYSTEM_CONFIG", record_id=config_key, old_value=old_value, new_value=payload.config_value,
        ip_address=request.client.host if request.client else None,
    )
    return _to_out(row)
