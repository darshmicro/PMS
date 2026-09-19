from datetime import datetime

from pydantic import BaseModel


class SystemConfigOut(BaseModel):
    config_id: int
    config_key: str
    config_value: str | None
    description: str | None
    modified_by: int | None
    modified_at: datetime


class SystemConfigUpsertIn(BaseModel):
    config_value: str | None = None
    description: str | None = None
