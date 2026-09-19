import pytest
from fastapi import HTTPException

from app.services.band_validation import check_no_overlap, validate_band


def test_valid_band_passes():
    validate_band(90.0, 99.99)  # should not raise


def test_inverted_band_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        validate_band(99.0, 90.0)
    assert exc_info.value.status_code == 400


def test_non_overlapping_bands_pass():
    existing = [(110.0, 999.0, 1), (105.0, 109.99, 2), (100.0, 104.99, 3)]
    check_no_overlap(existing, 90.0, 99.99)  # should not raise


def test_overlapping_bands_are_rejected():
    existing = [(100.0, 104.99, 1)]
    with pytest.raises(HTTPException) as exc_info:
        check_no_overlap(existing, 102.0, 108.0)
    assert exc_info.value.status_code == 409


def test_touching_boundary_counts_as_overlap():
    # Spec's own example uses 105-109.99 and 100-104.99 (half-open by
    # design) - a naive 100-105 next to 105-110 would touch at 105 and
    # is rejected here so the caller is forced to pick non-touching bounds.
    existing = [(100.0, 105.0, 1)]
    with pytest.raises(HTTPException):
        check_no_overlap(existing, 105.0, 110.0)


def test_exclude_id_allows_updating_a_rule_in_place():
    existing = [(100.0, 104.99, 1), (105.0, 109.99, 2)]
    # Updating rule 1's own range slightly should not conflict with itself
    check_no_overlap(existing, 99.0, 104.99, exclude_id=1)
