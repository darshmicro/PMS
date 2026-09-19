from datetime import datetime

from pydantic import BaseModel


class AttachmentOut(BaseModel):
    attachment_id: int
    employee_kpi_id: int | None
    related_employee_id: int | None
    file_name: str
    file_version: int
    uploaded_by: str
    uploaded_at: datetime
