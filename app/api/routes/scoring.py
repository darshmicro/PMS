"""
KPI Scoring Rules + Rating Master endpoints (spec Sections 12/21). Both
are "value falls in exactly one range" masters - validated with the
shared band_validation helpers so two active ranges can never overlap
(see that module's docstring for why that matters for scoring
correctness, not just data hygiene).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.performance_masters import KPIMaster, KPIScoringRule, RatingMaster
from app.schemas.scoring import (
    KPIScoringRuleCreate,
    KPIScoringRuleOut,
    KPIScoringRuleUpdate,
    RatingMasterCreate,
    RatingMasterOut,
    RatingMasterUpdate,
)
from app.services.audit_service import write_audit
from app.services.band_validation import check_no_overlap, validate_band
from app.services.export_service import build_export_workbook

router = APIRouter(prefix="/masters", tags=["scoring"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ============================================================= KPI Scoring Rules

def _rule_to_out(r: KPIScoringRule) -> KPIScoringRuleOut:
    return KPIScoringRuleOut(
        rule_id=r.RuleID, kpi_id=r.KPIID, kpi_name=r.kpi.KPIName if r.kpi else None,
        min_achievement=r.MinAchievement, max_achievement=r.MaxAchievement,
        score=r.Score, is_active=r.IsActive,
    )


@router.get("/scoring-rules", response_model=list[KPIScoringRuleOut])
def list_scoring_rules(
    kpi_id: int | None = None, active_only: bool | None = None, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW")),
):
    query = db.query(KPIScoringRule)
    # kpi_id=0 is used as a sentinel by the frontend to mean "global rules only" (KPIID IS NULL)
    if kpi_id is not None:
        query = query.filter(KPIScoringRule.KPIID == (kpi_id or None))
    if active_only is not None:
        query = query.filter(KPIScoringRule.IsActive == active_only)
    return [_rule_to_out(r) for r in query.order_by(KPIScoringRule.MinAchievement).all()]


@router.post("/scoring-rules", response_model=KPIScoringRuleOut, status_code=status.HTTP_201_CREATED)
def create_scoring_rule(
    payload: KPIScoringRuleCreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    if payload.kpi_id is not None and db.get(KPIMaster, payload.kpi_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="KPI not found")
    if not (1 <= payload.score <= 5):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Score must be between 1 and 5")
    validate_band(payload.min_achievement, payload.max_achievement)

    existing = (
        db.query(KPIScoringRule)
        .filter(KPIScoringRule.KPIID == payload.kpi_id, KPIScoringRule.IsActive == True)  # noqa: E712
        .all()
    )
    check_no_overlap(
        [(r.MinAchievement, r.MaxAchievement, r.RuleID) for r in existing],
        payload.min_achievement, payload.max_achievement,
    )

    rule = KPIScoringRule(
        KPIID=payload.kpi_id, MinAchievement=payload.min_achievement,
        MaxAchievement=payload.max_achievement, Score=payload.score,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="CREATE", module="SCORING_RULES", record_id=str(rule.RuleID),
        new_value=f"KPIID={payload.kpi_id}, range={payload.min_achievement}-{payload.max_achievement}, "
                  f"score={payload.score}",
        ip_address=_client_ip(request),
    )
    return _rule_to_out(rule)


@router.put("/scoring-rules/{rule_id}", response_model=KPIScoringRuleOut)
def update_scoring_rule(
    rule_id: int, payload: KPIScoringRuleUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    rule = db.get(KPIScoringRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Scoring rule not found")

    new_min = payload.min_achievement if payload.min_achievement is not None else rule.MinAchievement
    new_max = payload.max_achievement if payload.max_achievement is not None else rule.MaxAchievement
    new_score = payload.score if payload.score is not None else rule.Score
    if not (1 <= new_score <= 5):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Score must be between 1 and 5")
    validate_band(new_min, new_max)

    existing = (
        db.query(KPIScoringRule)
        .filter(KPIScoringRule.KPIID == rule.KPIID, KPIScoringRule.IsActive == True)  # noqa: E712
        .all()
    )
    check_no_overlap(
        [(r.MinAchievement, r.MaxAchievement, r.RuleID) for r in existing],
        new_min, new_max, exclude_id=rule_id,
    )

    old_value = f"range={rule.MinAchievement}-{rule.MaxAchievement}, score={rule.Score}"
    rule.MinAchievement, rule.MaxAchievement, rule.Score = new_min, new_max, new_score
    db.commit()
    db.refresh(rule)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="EDIT", module="SCORING_RULES", record_id=str(rule_id),
        old_value=old_value, new_value=f"range={new_min}-{new_max}, score={new_score}",
        reason=payload.reason, ip_address=_client_ip(request),
    )
    return _rule_to_out(rule)


@router.post("/scoring-rules/{rule_id}/deactivate", response_model=KPIScoringRuleOut)
def deactivate_scoring_rule(
    rule_id: int, reason: str, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    rule = db.get(KPIScoringRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Scoring rule not found")
    rule.IsActive = False
    db.commit()

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="DEACTIVATE", module="SCORING_RULES", record_id=str(rule_id),
        reason=reason, ip_address=_client_ip(request),
    )
    return _rule_to_out(rule)


@router.get("/scoring-rules/export")
def export_scoring_rules(
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW"))
):
    rows = db.query(KPIScoringRule).order_by(KPIScoringRule.KPIID, KPIScoringRule.MinAchievement).all()
    content = build_export_workbook(
        sheet_title="KPI Scoring Rules",
        headers=["KPI", "Min Achievement %", "Max Achievement %", "Score", "Active"],
        rows=[
            [r.kpi.KPIName if r.kpi else "Global Default", r.MinAchievement, r.MaxAchievement,
             r.Score, "Yes" if r.IsActive else "No"]
            for r in rows
        ],
        generated_by=ctx.ad_username,
        context_label="Master Export - KPI Scoring Rules",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=KPI_Scoring_Rules.xlsx"},
    )


# ==================================================================== Rating Master

def _rating_to_out(r: RatingMaster) -> RatingMasterOut:
    return RatingMasterOut(
        rating_id=r.RatingID, rating_label=r.RatingLabel,
        min_percent=r.MinPercent, max_percent=r.MaxPercent, is_active=r.IsActive,
    )


@router.get("/ratings", response_model=list[RatingMasterOut])
def list_ratings(
    active_only: bool | None = None, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW")),
):
    query = db.query(RatingMaster)
    if active_only is not None:
        query = query.filter(RatingMaster.IsActive == active_only)
    return [_rating_to_out(r) for r in query.order_by(RatingMaster.MinPercent.desc()).all()]


@router.post("/ratings", response_model=RatingMasterOut, status_code=status.HTTP_201_CREATED)
def create_rating(
    payload: RatingMasterCreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    validate_band(payload.min_percent, payload.max_percent)
    existing = db.query(RatingMaster).filter(RatingMaster.IsActive == True).all()  # noqa: E712
    check_no_overlap(
        [(r.MinPercent, r.MaxPercent, r.RatingID) for r in existing],
        payload.min_percent, payload.max_percent,
    )

    rating = RatingMaster(
        RatingLabel=payload.rating_label, MinPercent=payload.min_percent, MaxPercent=payload.max_percent,
    )
    db.add(rating)
    db.commit()
    db.refresh(rating)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="CREATE", module="RATING_MASTER", record_id=str(rating.RatingID),
        new_value=f"{payload.rating_label}: {payload.min_percent}-{payload.max_percent}%",
        ip_address=_client_ip(request),
    )
    return _rating_to_out(rating)


@router.put("/ratings/{rating_id}", response_model=RatingMasterOut)
def update_rating(
    rating_id: int, payload: RatingMasterUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.EDIT")),
):
    rating = db.get(RatingMaster, rating_id)
    if rating is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rating not found")

    new_min = payload.min_percent if payload.min_percent is not None else rating.MinPercent
    new_max = payload.max_percent if payload.max_percent is not None else rating.MaxPercent
    new_label = payload.rating_label if payload.rating_label is not None else rating.RatingLabel
    validate_band(new_min, new_max)

    existing = db.query(RatingMaster).filter(RatingMaster.IsActive == True).all()  # noqa: E712
    check_no_overlap(
        [(r.MinPercent, r.MaxPercent, r.RatingID) for r in existing], new_min, new_max, exclude_id=rating_id,
    )

    old_value = f"{rating.RatingLabel}: {rating.MinPercent}-{rating.MaxPercent}%"
    rating.RatingLabel, rating.MinPercent, rating.MaxPercent = new_label, new_min, new_max
    db.commit()
    db.refresh(rating)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="EDIT", module="RATING_MASTER", record_id=str(rating_id),
        old_value=old_value, new_value=f"{new_label}: {new_min}-{new_max}%",
        reason=payload.reason, ip_address=_client_ip(request),
    )
    return _rating_to_out(rating)


@router.post("/ratings/{rating_id}/deactivate", response_model=RatingMasterOut)
def deactivate_rating(
    rating_id: int, reason: str, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MASTERS.DEACTIVATE")),
):
    rating = db.get(RatingMaster, rating_id)
    if rating is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rating not found")
    rating.IsActive = False
    db.commit()

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="DEACTIVATE", module="RATING_MASTER", record_id=str(rating_id),
        reason=reason, ip_address=_client_ip(request),
    )
    return _rating_to_out(rating)


@router.get("/ratings/export")
def export_ratings(db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MASTERS.VIEW"))):
    rows = db.query(RatingMaster).order_by(RatingMaster.MinPercent.desc()).all()
    content = build_export_workbook(
        sheet_title="Rating Master",
        headers=["Rating Label", "Min %", "Max %", "Active"],
        rows=[[r.RatingLabel, r.MinPercent, r.MaxPercent, "Yes" if r.IsActive else "No"] for r in rows],
        generated_by=ctx.ad_username,
        context_label="Master Export - Ratings",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Rating_Master.xlsx"},
    )
