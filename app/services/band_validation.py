"""
Shared band-validation logic for KPI_Scoring_Rules and Rating_Master (spec
Sections 12/21). Both are "a value falls in exactly one range" masters -
scoring bands map achievement% to a 1-5 score, rating bands map final
score% to a label - and both must never let two active bands overlap,
or a percentage in the overlap would resolve to two different
scores/ratings depending on which row the query happened to return first.
"""
from fastapi import HTTPException, status


def validate_band(min_value: float, max_value: float) -> None:
    if min_value > max_value:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Minimum ({min_value}) must not be greater than maximum ({max_value})",
        )


def check_no_overlap(
    existing_bands: list[tuple[float, float, int]],
    new_min: float,
    new_max: float,
    exclude_id: int | None = None,
) -> None:
    """
    existing_bands: list of (min, max, id) for other active bands in the
    same set (same KPIID for scoring rules, or the whole active Rating_Master
    for ratings - there's only one rating scale at a time).
    Two closed intervals [a,b] and [c,d] overlap iff a <= d and c <= b;
    touching endpoints (one band's max equal to the next band's min) are
    treated as an overlap too, since a value AT that boundary would
    otherwise match two bands - callers should use half-open-style
    boundaries (e.g. 90-99, 100-104) to avoid touching by design.
    """
    for existing_min, existing_max, existing_id in existing_bands:
        if exclude_id is not None and existing_id == exclude_id:
            continue
        if new_min <= existing_max and existing_min <= new_max:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"Range {new_min}-{new_max} overlaps an existing active range "
                    f"{existing_min}-{existing_max}"
                ),
            )
