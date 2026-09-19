"""
Integration-level tests: exercise the actual DB query + overlap-check
sequence the scoring/rating routes perform (query active bands, then
validate), not just the pure validator functions in isolation.
"""
import pytest
from fastapi import HTTPException

from app.models.performance_masters import KPIMaster, KPAMaster, KPIScoringRule, RatingMaster
from app.services.band_validation import check_no_overlap, validate_band


def _seed_kpi(db_session) -> KPIMaster:
    kpa = KPAMaster(KPACode="KPA-T1", KPAName="Test KPA", IsActive=True)
    db_session.add(kpa)
    db_session.flush()
    kpi = KPIMaster(
        KPICode="KPI-T1", KPIName="Test KPI", KPAID=kpa.KPAID, MeasurementType="PERCENTAGE", IsActive=True,
    )
    db_session.add(kpi)
    db_session.commit()
    return kpi


def test_kpi_specific_scoring_rules_do_not_conflict_with_global_rules(db_session):
    kpi = _seed_kpi(db_session)

    # Global default rule (KPIID=None) covering 90-99
    global_rule = KPIScoringRule(KPIID=None, MinAchievement=90.0, MaxAchievement=99.99, Score=2, IsActive=True)
    db_session.add(global_rule)
    db_session.commit()

    # A KPI-specific rule for the SAME range is fine - it's scoped to a
    # different KPIID bucket, so the overlap check (scoped by KPIID in the
    # route) must not compare it against the global set.
    kpi_specific_existing = (
        db_session.query(KPIScoringRule)
        .filter(KPIScoringRule.KPIID == kpi.KPIID, KPIScoringRule.IsActive == True)  # noqa: E712
        .all()
    )
    assert kpi_specific_existing == []  # no KPI-specific rules yet, so no overlap possible
    check_no_overlap([(r.MinAchievement, r.MaxAchievement, r.RuleID) for r in kpi_specific_existing], 90.0, 99.99)


def test_second_overlapping_rule_for_same_kpi_is_rejected(db_session):
    kpi = _seed_kpi(db_session)
    rule1 = KPIScoringRule(KPIID=kpi.KPIID, MinAchievement=100.0, MaxAchievement=104.99, Score=3, IsActive=True)
    db_session.add(rule1)
    db_session.commit()

    existing = (
        db_session.query(KPIScoringRule)
        .filter(KPIScoringRule.KPIID == kpi.KPIID, KPIScoringRule.IsActive == True)  # noqa: E712
        .all()
    )
    with pytest.raises(HTTPException) as exc_info:
        check_no_overlap(
            [(r.MinAchievement, r.MaxAchievement, r.RuleID) for r in existing], 102.0, 110.0,
        )
    assert exc_info.value.status_code == 409


def test_rating_master_bands_from_spec_example_do_not_overlap(db_session):
    bands = [
        ("Exceptional", 90.00, 100.00),
        ("Exceeds Expectations", 80.00, 89.99),
        ("Meets Expectations", 70.00, 79.99),
        ("Partially Meets Expectations", 60.00, 69.99),
        ("Does Not Meet Expectations", 0.00, 59.99),
    ]
    for label, lo, hi in bands:
        validate_band(lo, hi)
        existing = db_session.query(RatingMaster).filter(RatingMaster.IsActive == True).all()  # noqa: E712
        check_no_overlap([(r.MinPercent, r.MaxPercent, r.RatingID) for r in existing], lo, hi)
        db_session.add(RatingMaster(RatingLabel=label, MinPercent=lo, MaxPercent=hi, IsActive=True))
        db_session.commit()

    assert db_session.query(RatingMaster).count() == 5


def test_deactivated_band_is_excluded_from_overlap_check(db_session):
    old_rule = KPIScoringRule(KPIID=None, MinAchievement=90.0, MaxAchievement=99.99, Score=2, IsActive=False)
    db_session.add(old_rule)
    db_session.commit()

    active_only = (
        db_session.query(KPIScoringRule)
        .filter(KPIScoringRule.KPIID.is_(None), KPIScoringRule.IsActive == True)  # noqa: E712
        .all()
    )
    assert active_only == []
    # A new rule covering the same range as the deactivated one is fine.
    check_no_overlap([(r.MinAchievement, r.MaxAchievement, r.RuleID) for r in active_only], 90.0, 99.99)
