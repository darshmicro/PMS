"""
Audit Log viewer business rules (spec Section 5/7/32 / M26). Every
mutating endpoint since M1 already writes to Audit_Log via
audit_service.write_audit() - that table and its insert-only DB-grant
enforcement (no UPDATE/DELETE for the application login) have existed
since the very first module. What has never existed until now is a
*reader* over it - this module is that reader, and nothing else: there is
no edit endpoint anywhere in this API for Audit_Log, matching the RBAC
matrix's own "V(all, no edit)" note for System Administrator, which in
practice is true for every role (nobody edits an audit trail, ever).

DESIGN NOTE on scope: unlike almost every other module, Audit Log HAS an
explicit RBAC matrix row - "X | X | X | V(dept) | V(plant) | V(all) |
V(all) | V(all, no edit)" for Employee/Manager/HOD/HR/Plant Head/MD/HR
Administrator/System Administrator. Three things are worth flagging
explicitly because they read differently from every other module's
scoping:

1. Employee/Manager/HOD get "X" (no access at all), not a self/team/dept
   view the way Dashboards (M24) and Reports (M25) give every role
   *something*. That "X" is enforced simply by never granting them
   AUDIT_LOG.VIEW at all - there is no in-app scope filter for them to
   fall through to, because require_permission() already turns them away
   with 403 before any query runs.

2. HR is dept-scoped here, not org-wide the way HR is in every other
   module's RBAC row (Employee Master, Masters, Performance Cycle, etc. -
   all "C,V,E" for HR with no department qualifier). An audit trail is
   more sensitive than the records it describes, so the spec narrows HR's
   own reach here specifically, rather than reusing HR's usual org-wide
   grant - flagged since it would be easy to assume HR should see
   everything the way it does everywhere else in this codebase and it
   deliberately does not.

3. MD and HR Administrator both get "V(all)" here, matching System
   Administrator's own "V(all, no edit)" - the three broadest roles in
   this table, with Plant Head narrowed to "V(plant)" (mirroring the same
   plant-matching rule M16/M24/M25 already use) rather than joining MD/HR
   Administrator's org-wide reach.

DESIGN NOTE on rows with no EmployeeID: Audit_Log.EmployeeID is nullable
(e.g. a failed login attempt before any employee is resolved). Such rows
have no department or plant to scope against, so they are excluded from
HR's and Plant Head's scoped views entirely (there is no employee to
compare) but remain visible in the org-wide "V(all)" views (MD/HR
Administrator/System Administrator) exactly as recorded.
"""
from sqlalchemy import false
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext
from app.models.audit import AuditLog
from app.models.employee import Employee

SCOPE_DEPT = "DEPT"
SCOPE_PLANT = "PLANT"
SCOPE_ALL = "ALL"


def apply_audit_scope(query, db: Session, ctx: CurrentContext) -> tuple:
    """Returns (scoped_query, scope_label). Only ever called after
    require_permission("AUDIT_LOG.VIEW") has already turned away
    Employee/Manager/HOD (the matrix's "X"), so every caller reaching
    here is HR, Plant Head, MD, HR Administrator or System Administrator."""
    role_codes = set(ctx.role_codes)
    if role_codes & {"MD", "HR_ADMIN", "SYS_ADMIN"}:
        return query, SCOPE_ALL
    if "PLANT_HEAD" in role_codes:
        acting = db.get(Employee, ctx.employee_id) if ctx.employee_id is not None else None
        plant_id = acting.PlantID if acting is not None else None
        query = query.join(Employee, AuditLog.EmployeeID == Employee.EmployeeID)
        if plant_id is None:
            # No plant on file for the acting Plant Head - an IS NULL
            # filter would over-match every *other* plant-less employee's
            # rows, so this is an explicit always-false filter instead
            # (same "no identity -> empty scope" principle as
            # Notification's _own_query, M23).
            return query.filter(false()), SCOPE_PLANT
        return query.filter(Employee.PlantID == plant_id), SCOPE_PLANT
    # HR
    acting = db.get(Employee, ctx.employee_id) if ctx.employee_id is not None else None
    department_id = acting.DepartmentID if acting is not None else None
    query = query.join(Employee, AuditLog.EmployeeID == Employee.EmployeeID)
    if department_id is None:
        return query.filter(false()), SCOPE_DEPT
    return query.filter(Employee.DepartmentID == department_id), SCOPE_DEPT
