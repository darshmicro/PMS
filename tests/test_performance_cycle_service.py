import pytest
from fastapi import HTTPException

from app.services.performance_cycle_service import validate_cycle_dates


def test_valid_sequential_cycle_passes():
    validate_cycle_dates({
        "KPISettingStart": "2026-04-01", "KPISettingEnd": "2026-04-30",
        "SelfAssessmentStart": "2027-04-01", "SelfAssessmentEnd": "2027-04-10",
        "ManagerReviewStart": "2027-04-11", "ManagerReviewEnd": "2027-04-20",
    })  # should not raise


def test_stage_start_after_own_end_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        validate_cycle_dates({"KPISettingStart": "2026-04-30", "KPISettingEnd": "2026-04-01"})
    assert exc_info.value.status_code == 400
    assert "KPI Setting" in exc_info.value.detail


def test_next_stage_starting_before_previous_ends_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        validate_cycle_dates({
            "KPISettingEnd": "2026-04-30",
            "SelfAssessmentStart": "2026-04-15",  # starts before KPI Setting even ends
        })
    assert exc_info.value.status_code == 400
    assert "Self Assessment" in exc_info.value.detail


def test_partial_dates_do_not_raise():
    # A cycle mid-configuration (only some stages dated yet) should not
    # be rejected just because later stages are still unset.
    validate_cycle_dates({"KPISettingStart": "2026-04-01", "KPISettingEnd": "2026-04-30"})
