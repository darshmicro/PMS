import pytest
from fastapi import HTTPException

from app.models.pip import PIP
from app.services.pip_service import (
    EXTENDED,
    SUCCESSFUL,
    UNSUCCESSFUL,
    close_pip,
    ensure_can_act,
    ensure_open,
    stamp_updated,
    validate_outcome,
)


def test_valid_outcomes_pass():
    for value in (SUCCESSFUL, UNSUCCESSFUL, EXTENDED):
        validate_outcome(value)  # should not raise


def test_invalid_outcome_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        validate_outcome("STILL_TRYING")
    assert exc_info.value.status_code == 400


def test_ensure_open_passes_when_outcome_none():
    pip = PIP(EmployeeID=1, Outcome=None)
    ensure_open(pip)  # should not raise


def test_ensure_open_rejects_closed_pip():
    pip = PIP(EmployeeID=1, Outcome=SUCCESSFUL)
    with pytest.raises(HTTPException) as exc_info:
        ensure_open(pip)
    assert exc_info.value.status_code == 409


def test_ensure_can_act_allows_broad_access_regardless_of_manager():
    pip = PIP(EmployeeID=1, ManagerID=5)
    ensure_can_act(pip, employee_id=999, is_broad_access=True)  # should not raise


def test_ensure_can_act_allows_assigned_manager():
    pip = PIP(EmployeeID=1, ManagerID=5)
    ensure_can_act(pip, employee_id=5, is_broad_access=False)  # should not raise


def test_ensure_can_act_rejects_unassigned_non_broad_caller():
    pip = PIP(EmployeeID=1, ManagerID=5)
    with pytest.raises(HTTPException) as exc_info:
        ensure_can_act(pip, employee_id=6, is_broad_access=False)
    assert exc_info.value.status_code == 403


def test_close_pip_sets_outcome_comments_and_timestamp():
    pip = PIP(EmployeeID=1)
    assert pip.UpdatedAt is None
    close_pip(pip, SUCCESSFUL, "Met all targets")
    assert pip.Outcome == SUCCESSFUL
    assert pip.Comments == "Met all targets"
    assert pip.UpdatedAt is not None


def test_close_pip_rejects_invalid_outcome():
    pip = PIP(EmployeeID=1)
    with pytest.raises(HTTPException) as exc_info:
        close_pip(pip, "MAYBE", None)
    assert exc_info.value.status_code == 400
    assert pip.Outcome is None


def test_stamp_updated_sets_updated_at():
    pip = PIP(EmployeeID=1)
    assert pip.UpdatedAt is None
    stamp_updated(pip)
    assert pip.UpdatedAt is not None
