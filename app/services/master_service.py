"""
All organization masters (Company, Plant, Department, Section,
Designation, Grade, Employee Category) follow the same lifecycle rules
from spec Section 6: Add/Edit/View/Activate/Deactivate/Search, no hard
delete, every change audited. Rather than duplicating that logic seven
times, routes call these generic functions with the model class and its
attribute names as parameters. Per-entity validation that genuinely
differs (e.g. "does this Plant's CompanyID exist") stays in the route.
"""
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext
from app.services.audit_service import write_audit


@dataclass
class MasterFieldConfig:
    model: type
    pk_attr: str
    code_attr: str
    name_attr: str
    module: str  # audit Module value, e.g. "MASTERS.DEPARTMENT"


def list_records(
    db: Session, cfg: MasterFieldConfig, search: str | None = None, active_only: bool | None = None
) -> list[Any]:
    query = db.query(cfg.model)
    if active_only is not None:
        query = query.filter(getattr(cfg.model, "IsActive") == active_only)
    if search:
        code_col = getattr(cfg.model, cfg.code_attr)
        name_col = getattr(cfg.model, cfg.name_attr)
        like = f"%{search}%"
        query = query.filter((code_col.ilike(like)) | (name_col.ilike(like)))
    return query.order_by(getattr(cfg.model, cfg.code_attr)).all()


def get_record(db: Session, cfg: MasterFieldConfig, record_id: int) -> Any:
    instance = db.get(cfg.model, record_id)
    if instance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{cfg.model.__name__} not found")
    return instance


def create_record(
    db: Session,
    cfg: MasterFieldConfig,
    data: dict,
    ctx: CurrentContext,
    ip_address: str | None,
) -> Any:
    code_value = data.get(cfg.code_attr)
    existing = (
        db.query(cfg.model).filter(getattr(cfg.model, cfg.code_attr) == code_value).one_or_none()
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"{cfg.model.__name__} code '{code_value}' already exists"
        )

    instance = cfg.model(**data)
    db.add(instance)
    db.commit()
    db.refresh(instance)

    write_audit(
        db,
        user_id=ctx.user_id,
        ad_username=ctx.ad_username,
        employee_id=ctx.employee_id,
        action="CREATE",
        module=cfg.module,
        record_id=str(getattr(instance, cfg.pk_attr)),
        new_value=str(data),
        ip_address=ip_address,
    )
    return instance


def update_record(
    db: Session,
    cfg: MasterFieldConfig,
    record_id: int,
    data: dict,
    ctx: CurrentContext,
    ip_address: str | None,
) -> Any:
    instance = get_record(db, cfg, record_id)

    old_value = {field: getattr(instance, field) for field in data}
    for field, value in data.items():
        setattr(instance, field, value)
    db.commit()
    db.refresh(instance)

    write_audit(
        db,
        user_id=ctx.user_id,
        ad_username=ctx.ad_username,
        employee_id=ctx.employee_id,
        action="EDIT",
        module=cfg.module,
        record_id=str(record_id),
        old_value=str(old_value),
        new_value=str(data),
        ip_address=ip_address,
    )
    return instance


def set_active_status(
    db: Session,
    cfg: MasterFieldConfig,
    record_id: int,
    is_active: bool,
    reason: str,
    ctx: CurrentContext,
    ip_address: str | None,
) -> Any:
    instance = get_record(db, cfg, record_id)
    old_status = instance.IsActive
    instance.IsActive = is_active
    db.commit()
    db.refresh(instance)

    write_audit(
        db,
        user_id=ctx.user_id,
        ad_username=ctx.ad_username,
        employee_id=ctx.employee_id,
        action="DEACTIVATE" if not is_active else "ACTIVATE",
        module=cfg.module,
        record_id=str(record_id),
        old_value=f"IsActive={old_status}",
        new_value=f"IsActive={is_active}",
        reason=reason,
        ip_address=ip_address,
    )
    return instance
