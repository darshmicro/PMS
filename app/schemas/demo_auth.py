from pydantic import BaseModel, Field


class DemoSetPasswordRequest(BaseModel):
    """Admin reset/first-time set - AUTH_MODE=demo_local only."""
    new_password: str = Field(min_length=8)


class DemoChangePasswordRequest(BaseModel):
    """Self-service change - AUTH_MODE=demo_local only."""
    current_password: str
    new_password: str = Field(min_length=8)
