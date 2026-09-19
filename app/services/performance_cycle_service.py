"""
Performance Cycle validation (spec Section 9). A cycle's dates gate which
workflow stage is currently open (read by the workflow engine in M19), so
bad dates here don't just look wrong in a form - they'd silently lock
every employee out of whichever stage got misconfigured. Validated here
at the service layer, not just in the browser (spec Section 33/49).
"""
from fastapi import HTTPException, status

# (start_field, end_field, human label), in the mandated stage order (Section 9/15).
STAGE_FIELDS = [
    ("KPISettingStart", "KPISettingEnd", "KPI Setting"),
    ("SelfAssessmentStart", "SelfAssessmentEnd", "Self Assessment"),
    ("ManagerReviewStart", "ManagerReviewEnd", "Manager Review"),
    ("HODReviewStart", "HODReviewEnd", "HOD Review"),
    ("HRReviewStart", "HRReviewEnd", "HR Review"),
    ("PlantHeadApprovalStart", "PlantHeadApprovalEnd", "Plant Head Approval"),
    ("MDApprovalStart", "MDApprovalEnd", "MD Approval"),
]


def validate_cycle_dates(merged: dict) -> None:
    """
    `merged` is the full set of stage date fields the cycle will have after
    the pending create/update is applied (existing values merged with the
    incoming change) - so an update to just one stage is still validated
    against the whole cycle's timeline.
    """
    # Each stage's own start must not be after its own end.
    for start_key, end_key, label in STAGE_FIELDS:
        start, end = merged.get(start_key), merged.get(end_key)
        if start is not None and end is not None and start > end:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"{label}: start date ({start}) must not be after end date ({end})",
            )

    # Stages must not overlap the next stage in the mandated sequence -
    # only checked where both boundary dates are actually set, since a
    # cycle may still be mid-configuration.
    for (_, end_key, end_label), (next_start_key, _, next_label) in zip(STAGE_FIELDS, STAGE_FIELDS[1:]):
        end = merged.get(end_key)
        next_start = merged.get(next_start_key)
        if end is not None and next_start is not None and next_start < end:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"{next_label} cannot start ({next_start}) before "
                    f"{end_label} ends ({end})"
                ),
            )
