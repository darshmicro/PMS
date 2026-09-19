"""
Single write path for Audit_Log so every module records changes the same
way (spec Section 32). M26 builds the *viewer*; this is the writer every
other module calls.
"""
from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def write_audit(
    db: Session,
    *,
    user_id: int | None,
    ad_username: str | None,
    employee_id: int | None,
    action: str,
    module: str,
    record_id: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    reason: str | None = None,
    ip_address: str | None = None,
) -> None:
    entry = AuditLog(
        UserID=user_id,
        ADUsername=ad_username,
        EmployeeID=employee_id,
        Action=action,
        Module=module,
        RecordID=record_id,
        OldValue=old_value,
        NewValue=new_value,
        Reason=reason,
        IPAddress=ip_address,
    )
    db.add(entry)
    db.commit()
