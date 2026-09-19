import pytest
from fastapi import HTTPException

from app.models.development_plan import COMPLETED, IN_PROGRESS, PENDING, DevelopmentPlan
from app.services.development_plan_service import stamp_updated, validate_completion_status


def test_valid_completion_statuses_pass():
    for value in (PENDING, IN_PROGRESS, COMPLETED):
        validate_completion_status(value)  # should not raise


def test_invalid_completion_status_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        validate_completion_status("DONE")
    assert exc_info.value.status_code == 400


def test_stamp_updated_sets_updated_at():
    plan = DevelopmentPlan(PerformanceID=1)
    assert plan.UpdatedAt is None
    stamp_updated(plan)
    assert plan.UpdatedAt is not None
