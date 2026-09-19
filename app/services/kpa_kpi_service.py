"""
KPA/KPI-specific validation (spec Sections 7/8) that sits on top of the
generic master_service CRUD: weightage bounds, effective-date ordering,
target ordering, and measurement-type/parent-reference checks that a
plain code/name master doesn't need.
"""
from fastapi import HTTPException, status

from app.models.performance_masters import MEASUREMENT_TYPES


def validate_weightage(weightage: float | None, field_label: str = "Weightage") -> None:
    if weightage is None:
        return
    if weightage < 0 or weightage > 100:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"{field_label} must be between 0 and 100, got {weightage}"
        )


def validate_effective_dates(effective_from, effective_to) -> None:
    if effective_from is not None and effective_to is not None and effective_from > effective_to:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Effective From ({effective_from}) must not be after Effective To ({effective_to})",
        )


def validate_measurement_type(measurement_type: str) -> None:
    if measurement_type not in MEASUREMENT_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid measurement type '{measurement_type}'. Must be one of: {', '.join(MEASUREMENT_TYPES)}",
        )


def validate_target_ordering(minimum, expected, stretch) -> None:
    """Only meaningful for numeric-style measurement types; callers pass
    None for any target not supplied and this simply skips those checks."""
    values = [("Minimum Target", minimum), ("Expected Target", expected), ("Stretch Target", stretch)]
    provided = [(label, v) for label, v in values if v is not None]
    for (label_a, val_a), (label_b, val_b) in zip(provided, provided[1:]):
        if val_a > val_b:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"{label_a} ({val_a}) must not be greater than {label_b} ({val_b})",
            )
