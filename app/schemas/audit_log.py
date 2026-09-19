from datetime import datetime

from pydantic import BaseModel


class AuditLogEntryOut(BaseModel):
    audit_id: int
    user_id: int | None
    ad_username: str | None
    employee_id: int | None
    action: str
    module: str
    record_id: str | None
    old_value: str | None
    new_value: str | None
    reason: str | None
    actioned_at: datetime
    ip_address: str | None
