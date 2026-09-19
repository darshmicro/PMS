"""
Scoring Engine (spec Section 8 / M18). Computes and permanently records
the figures spec Section 8.4/8.5 describe, and is invoked exactly once
per record - from MD Approval's `/approve` endpoint (M17), immediately
after `finalize_and_lock()` sets Status=FINAL_APPROVED - per Section 8.5's
own words: "only at the FINAL_APPROVED transition."

DESIGN NOTE on what "Final Score %" actually is here: Section 8.4 gives a
literal formula (KPI component % + Competency component % + calibration
adjustment). But this codebase's own review chain never computes that
sum directly - M14 gave HOD Review a single aggregate HODScore column
(the DDL only offers one), independently entered and only checked
against the KPI-weighted figure as a reference (requiring comments to
explain any divergence, never overridden by it), and M15 derived
HRReview.HRScore as HODScore + CalibrationAdjustment. That whole-record
score - not a fresh independent recomputation from raw components - is
the score that has actually been reviewed, calibrated and approved by
HR/Plant Head/MD by the time a record reaches FINAL_APPROVED. So the
FINAL figure recorded here, copied to Employee_Performance.FinalScorePct,
and used for rating derivation, is HRReview.HRScore itself - continuing
the exact "follow the concrete schema/whole-record-override chain over
the narrative formula" resolution established in M14 and reused in M15.
The KPI_WEIGHTED and COMPETENCY_WEIGHTED rows this module also writes to
Performance_Scores are the literal Section 8.2/8.3 component figures,
kept for audit/traceability of how the appraisal was scored - not
summed to produce FINAL, since HODScore already superseded that sum
wherever the two diverged.

DESIGN NOTE on the Competency component: Employee_Competency (see that
model's own docstring) has no owning assignment/scoring module in the
M1-M17 build sequence - a spec gap, not a decision made here. Rather than
blocking every appraisal in the system on a workflow that hasn't been
built, a record with zero assigned competencies gets a Competency
component of exactly 0 (a legitimate "this org isn't using competency
scoring yet" state). A record WITH assigned competencies that aren't
fully scored, however, is genuinely incomplete data - not a valid zero -
so that case is rejected the same way every other missing-prerequisite
case in this codebase is: loudly, before anything is written.
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.assignment import EmployeeKPA, EmployeeKPI, EmployeePerformance
from app.models.employee_competency import EmployeeCompetency
from app.models.hr_review import HRReview
from app.models.manager_review import ManagerReview
from app.models.performance_masters import RatingMaster
from app.models.performance_score import COMPETENCY_WEIGHTED, FINAL, KPI_WEIGHTED, PerformanceRating, PerformanceScore


def compute_kpi_weighted_pct(db: Session, performance: EmployeePerformance) -> float | None:
    """Section 8.2: Weighted KPI Score % = ManagerScore x KPIWeightage / 5,
    summed across every assigned KPI. Recorded for audit/traceability -
    see module docstring for why this figure is NOT what ends up in
    FinalScorePct. Returns None if any assigned KPI has no manager score
    yet, the same "no partial figures" rule M14 already established for
    its own reference calculation."""
    reviews_by_kpi = {
        r.EmployeeKPIID: r
        for r in (
            db.query(ManagerReview)
            .join(EmployeeKPI, ManagerReview.EmployeeKPIID == EmployeeKPI.EmployeeKPIID)
            .join(EmployeeKPA, EmployeeKPI.EmployeeKPAID == EmployeeKPA.EmployeeKPAID)
            .filter(EmployeeKPA.PerformanceID == performance.PerformanceID)
            .all()
        )
    }
    total = 0.0
    for employee_kpa in performance.kpas:
        for kpi in employee_kpa.kpis:
            review = reviews_by_kpi.get(kpi.EmployeeKPIID)
            if review is None or review.ManagerScore is None:
                return None
            total += float(review.ManagerScore) * float(kpi.Weightage) / 5.0
    return round(total, 2)


def compute_competency_weighted_pct(db: Session, performance_id: int) -> float:
    """Section 8.3: same weighting pattern as KPIs -
    Score x Weightage / 5, summed. Zero assigned competencies -> 0.0 (a
    valid state - see module docstring). Any assigned-but-unscored
    competency blocks finalization with a 400, since that's incomplete
    data, not "no competencies used"."""
    competencies = db.query(EmployeeCompetency).filter(EmployeeCompetency.PerformanceID == performance_id).all()
    if not competencies:
        return 0.0
    total = 0.0
    for ec in competencies:
        if ec.Score is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Employee_Competency {ec.EmployeeCompetencyID} has no Score recorded yet",
            )
        total += float(ec.Score) * float(ec.Weightage) / 5.0
    return round(total, 2)


def get_final_score(db: Session, performance_id: int) -> float:
    """The authoritative Final Score % - see module docstring for why
    this is HRReview.HRScore rather than a fresh KPI+Competency sum. A
    record should never legitimately reach here without one (MD Approval
    already requires it via get_hr_score), so a missing score is a 409
    data-integrity signal, not a 400 or a silent zero."""
    hr_review = db.query(HRReview).filter(HRReview.PerformanceID == performance_id).one_or_none()
    if hr_review is None or hr_review.HRScore is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This record has no completed HR Review & Calibration score to finalize",
        )
    return float(hr_review.HRScore)


def lookup_rating_band(db: Session, final_score_pct: float) -> RatingMaster:
    """Section 8.5: look up the active Rating_Master band containing
    FinalScorePct. Configurable bands, never hard-coded thresholds - the
    same principle M9's own Rating Master module was built to serve.
    A gap in HR's configured bands is a 409 (a data-configuration
    problem, not something the requesting user did wrong), mirroring the
    no-scoring-band-covers-achievement guard from M12's self-assessment
    service."""
    band = (
        db.query(RatingMaster)
        .filter(
            RatingMaster.IsActive == True,  # noqa: E712
            RatingMaster.MinPercent <= final_score_pct,
            RatingMaster.MaxPercent >= final_score_pct,
        )
        .one_or_none()
    )
    if band is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"No active Rating Master band covers a final score of {final_score_pct}% - check the configured rating bands",
        )
    return band


def run_scoring_engine(db: Session, performance: EmployeePerformance, actioned_by_user_id: int | None) -> PerformanceRating:
    """Entry point called by MD Approval's /approve (M17), immediately
    after the record is finalized and locked. Writes the Performance_Scores
    audit rows, copies FINAL to Employee_Performance.FinalScorePct/FinalRatingID,
    and inserts the (immutable, insert-once) Performance_Ratings row.

    Idempotency: a record can only ever reach here once in the normal
    workflow (MD Approval's own ensure_stage_editable/IsLocked guard
    prevents a second /approve call), but as defense in depth this
    refuses to insert a second Performance_Ratings row for the same
    PerformanceID rather than violating its UniqueConstraint - existing
    scores/rating are treated as already-finalized and left untouched.
    """
    existing_rating = (
        db.query(PerformanceRating).filter(PerformanceRating.PerformanceID == performance.PerformanceID).one_or_none()
    )
    if existing_rating is not None:
        return existing_rating

    now = datetime.now(timezone.utc)
    kpi_weighted_pct = compute_kpi_weighted_pct(db, performance)
    competency_weighted_pct = compute_competency_weighted_pct(db, performance.PerformanceID)
    final_score_pct = get_final_score(db, performance.PerformanceID)
    rating = lookup_rating_band(db, final_score_pct)

    if kpi_weighted_pct is not None:
        db.add(PerformanceScore(
            PerformanceID=performance.PerformanceID, ScoreType=KPI_WEIGHTED,
            ScoreValue=kpi_weighted_pct, CalculatedAt=now,
        ))
    db.add(PerformanceScore(
        PerformanceID=performance.PerformanceID, ScoreType=COMPETENCY_WEIGHTED,
        ScoreValue=competency_weighted_pct, CalculatedAt=now,
    ))
    db.add(PerformanceScore(
        PerformanceID=performance.PerformanceID, ScoreType=FINAL,
        ScoreValue=final_score_pct, CalculatedAt=now,
    ))

    performance.FinalScorePct = final_score_pct
    performance.FinalRatingID = rating.RatingID

    performance_rating = PerformanceRating(
        PerformanceID=performance.PerformanceID, FinalScorePct=final_score_pct,
        RatingID=rating.RatingID, FinalizedAt=now,
    )
    db.add(performance_rating)
    db.flush()
    return performance_rating
