"""
Reports & Export Center endpoints (spec Section 5/7/36A / M25). See
report_service.py's docstring for why this module is small - 26 export
endpoints already exist across M3-M24, and this module adds only the
catalog and the one new cross-cutting report, not a rebuild of what
already shipped.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.schemas.report import AppraisalStatusReportOut, ReportCatalogEntryOut
from app.services.export_service import build_export_workbook
from app.services.report_service import build_appraisal_status_rows, list_available_reports, render_csv, render_pdf

router = APIRouter(prefix="/reports", tags=["reports"])

_APPRAISAL_STATUS_HEADERS = [
    "PerformanceID", "EmployeeCode", "EmployeeName", "Cycle", "Status", "FinalScorePct", "FinalRating", "IsLocked",
]


def _appraisal_status_export_rows(rows: list[dict]) -> list[list]:
    return [
        [
            r["performance_id"], r["employee_code"], r["employee_name"], r["cycle_name"], r["status"],
            r["final_score_pct"] if r["final_score_pct"] is not None else "", r["final_rating_label"] or "",
            "Yes" if r["is_locked"] else "No",
        ]
        for r in rows
    ]


@router.get("/catalog", response_model=list[ReportCatalogEntryOut])
def reports_catalog(ctx: CurrentContext = Depends(require_permission("REPORT.VIEW"))):
    return [ReportCatalogEntryOut(**entry) for entry in list_available_reports(ctx.permission_codes)]


@router.get("/appraisal-status")
def appraisal_status_report(
    cycle_id: int | None = None,
    employee_id: int | None = None,
    year: int | None = None,
    format: str = Query("json", pattern="^(json|xlsx|csv|pdf)$"),
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("REPORT.VIEW")),
):
    if "SYS_ADMIN" in ctx.role_codes:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="System Administrator has no access to the Reports & Export Center (RBAC matrix: X)",
        )

    rows, scope = build_appraisal_status_rows(db, ctx, cycle_id=cycle_id, employee_id=employee_id, year=year)

    if format == "json":
        return AppraisalStatusReportOut(scope=scope, rows=rows)

    export_rows = _appraisal_status_export_rows(rows)
    context_label = f"Appraisal Status - {scope} scope"
    filter_bits = [f"{k}={v}" for k, v in (("CycleID", cycle_id), ("EmployeeID", employee_id), ("Year", year)) if v is not None]
    filter_criteria = ", ".join(filter_bits) if filter_bits else "None"

    if format == "csv":
        content = render_csv(_APPRAISAL_STATUS_HEADERS, export_rows)
        return Response(
            content=content, media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=Appraisal_Status_Report.csv"},
        )
    if format == "pdf":
        content = render_pdf(
            title="Consolidated Appraisal Status Report", headers=_APPRAISAL_STATUS_HEADERS, rows=export_rows,
            generated_by=ctx.ad_username, context_label=context_label,
        )
        return Response(
            content=content, media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=Appraisal_Status_Report.pdf"},
        )
    # xlsx
    content = build_export_workbook(
        sheet_title="Appraisal Status", headers=_APPRAISAL_STATUS_HEADERS, rows=export_rows,
        generated_by=ctx.ad_username, context_label=context_label, filter_criteria=filter_criteria,
    )
    return Response(
        content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Appraisal_Status_Report.xlsx"},
    )
