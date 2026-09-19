from datetime import datetime

from pydantic import BaseModel


class NotificationOut(BaseModel):
    notification_id: int
    message: str
    module: str | None
    is_read: bool
    created_at: datetime


class UnreadCountOut(BaseModel):
    unread_count: int
