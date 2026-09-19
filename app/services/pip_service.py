"""
PIP business rules (spec Section 4.5 / M21). See the model module's
docstring for the design decisions this leans on: EmployeeID-scoped (not
tied to one appraisal cycle), HR-led authority with the assigned manager
able to work the day-to-day fields, and a one-way open->closed lifecycle
gated by Outcome.
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.models.pip import PIP

SUCCESSFUL = "SUCCESSFUL"
UNSUCCESSFUL = "UNSUCCESSFUL"
EXTENDED = "EXTENDED"
OUTCOMES = (SUCCESSFUL, UNSUCCESSFUL, EXTENDED)


def validate_outcome(value: str) -> None:
    if value not in OUTCOMES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"Outcome must be one of {', '.join(OUTCOMES)}, got '{value}'",
        )


def ensure_open(pip: PIP) -> None:
    """A PIP with an Outcome already recorded is closed - see model
    docstring for why this is a one-way transition, never reopened or
    re-edited in place here."""
    if pip.Outcome is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"This PIP is already closed (Outcome={pip.Outcome})")


def ensure_can_act(pip: PIP, employee_id: int | None, is_broad_access: bool) -> None:
    """HR/HR Administrator/Plant Head/MD may act on any PIP; the assigned
    manager (PIP.ManagerID, not Employee.ManagerID - see model docstring)
    may act only on PIPs they're personally assigned to."""
    if is_broad_access:
        return
    if pip.ManagerID != employee_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Only HR (or an equivalent role) or this PIP's assigned manager may act on it"
        )


def close_pip(pip: PIP, outcome: str, comments: str | None) -> None:
    validate_outcome(outcome)
    pip.Outcome = outcome
    pip.Comments = comments
    pip.UpdatedAt = datetime.now(timezone.utc)


def stamp_updated(pip: PIP) -> None:
    pip.UpdatedAt = datetime.now(timezone.utc)
