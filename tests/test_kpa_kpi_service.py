import pytest
from fastapi import HTTPException

from app.services.kpa_kpi_service import (
    validate_effective_dates,
    validate_measurement_type,
    validate_target_ordering,
    validate_weightage,
)


def test_weightage_within_bounds_passes():
    validate_weightage(20.0)
    validate_weightage(0.0)
    validate_weightage(100.0)
    validate_weightage(None)  # optional field, no value is fine


def test_weightage_over_100_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        validate_weightage(150.0)
    assert exc_info.value.status_code == 400


def test_weightage_negative_is_rejected():
    with pytest.raises(HTTPException):
        validate_weightage(-5.0)


def test_effective_dates_ordering():
    validate_effective_dates("2026-01-01", "2026-12-31")  # fine
    with pytest.raises(HTTPException):
        validate_effective_dates("2026-12-31", "2026-01-01")


def test_measurement_type_validation():
    validate_measurement_type("PERCENTAGE")
    with pytest.raises(HTTPException) as exc_info:
        validate_measurement_type("NOT_A_REAL_TYPE")
    assert exc_info.value.status_code == 400


def test_target_ordering_valid():
    validate_target_ordering(90.0, 100.0, 115.0)  # min <= expected <= stretch


def test_target_ordering_invalid():
    with pytest.raises(HTTPException):
        validate_target_ordering(100.0, 90.0, 115.0)  # min > expected


def test_target_ordering_with_missing_values_is_skipped():
    validate_target_ordering(None, 100.0, None)  # only expected given, nothing to compare
