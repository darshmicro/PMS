"""
Notification business rules (spec Section 4.5/7 / M23: "In-app + email,
stage-based triggers"). No RBAC matrix row exists for this module either
(Section 5's matrix never reaches it), but Section 7's Common screen #4,
"Notifications panel," is listed for every role alike - unlike every other
screen in that list, which is role-scoped. So NOTIFICATION.VIEW means
"your own notifications, and only your own" for every role including the
broad-access ones (HR/Plant Head/MD/HR Administrator): nobody has
visibility into anyone else's inbox, which is the opposite of every prior
module's self/reports/department/broad-access tiering.

Section 7's admin screen #35, "Notification Configuration," and the RBAC
matrix's own "System Configuration (SMTP, AD server, storage path)" row
(HR Administrator only) place SMTP/template configuration under System
Configuration (M28), not here - this module fires notifications using
whatever SMTP settings config.py already exposes (declared in M1, like
FILE_STORAGE_PATH before it, but unused until now), not a per-notification
configurable template engine of its own.

DESIGN NOTE on "stage-based triggers": rather than build a second,
parallel signal for "a transition just happened," this module hooks the
exact same call sites M19's Workflow Engine already established for that
purpose - record_transition(), called at 11 sites across 6 already-shipped
files (self_assessments.py x2, manager_reviews.py x2, hod_reviews.py x2,
hr_reviews.py x1, plant_head_approvals.py x2, md_approvals.py x2). Each
site gets one additional line - notify_stage_transition(db, performance) -
immediately after its existing record_transition() call, matching M19's
own additive-only retrofit principle (a single added call, never a
rewrite of the surrounding validation/transition logic).

DESIGN NOTE on recipients: the DDL gives Notifications a single
EmployeeID, not a role or a broadcast list, so "who gets notified when a
record reaches stage X" has to resolve to concrete employees. For stages
with a direct per-employee FK on Employees (ManagerID, HODID, HRID - all
from M4), that FK is the recipient. Plant Head and MD have no such FK
(Plant Head Approval's own ownership check, M16, compares PlantID rather
than a person - see that module's docstring), so those two resolve via
role membership instead: every active User holding the PLANT_HEAD role
whose own Employee.PlantID matches the reviewed employee's plant (mirrors
M16's own plant-matching rule), and every active User holding the MD role
org-wide (mirrors MD Approval's own org-wide scope, M17).
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.notification import Notification
from app.models.rbac import Role, User, UserRole

STAGE_RECIPIENT_KIND: dict[str, str] = {
    "EMPLOYEE_ACKNOWLEDGED": "SELF",
    "SELF_ASSESSMENT": "SELF",
    "MANAGER_REVIEW": "MANAGER",
    "HOD_REVIEW": "HOD",
    "HR_REVIEW": "HR",
    "PLANT_HEAD_APPROVAL": "PLANT_HEAD",
    "MD_APPROVAL": "MD",
    "FINAL_APPROVED": "SELF",
}

STAGE_MESSAGE: dict[str, str] = {
    "EMPLOYEE_ACKNOWLEDGED": "Your appraisal is ready - please acknowledge it and complete your self-assessment.",
    "SELF_ASSESSMENT": "Your self-assessment is in progress.",
    "MANAGER_REVIEW": "A self-assessment is ready for your Manager Review.",
    "HOD_REVIEW": "A review is ready for your HOD Review.",
    "HR_REVIEW": "A review is ready for HR Review & Calibration.",
    "PLANT_HEAD_APPROVAL": "A calibrated appraisal is ready for your Plant Head Approval.",
    "MD_APPROVAL": "An appraisal is ready for your MD Final Approval.",
    "FINAL_APPROVED": "Your appraisal has been finalized and approved.",
}


def send_email_hook(employee: Employee, message: str) -> None:
    """Spec Section 4.5's build-order description asks for "in-app +
    email" delivery. No SMTP relay is reachable from this environment (the
    workspace's own outbound network is allow-listed to package registries
    and GitHub only), so this is a documented no-op hook, the same pattern
    as attachment_service.virus_scan_hook(): a real deployment wires
    smtplib + settings.SMTP_SERVER/SMTP_PORT/SMTP_FROM (already declared
    in M1's config.py, unused until now) in here without touching any
    caller. As shipped, every in-app notification is routed through this
    function and it always passes through silently.
    """
    return None


def create_notification(db: Session, *, employee_id: int, message: str, module: str | None = None) -> Notification:
    notification = Notification(EmployeeID=employee_id, Message=message, Module=module)
    db.add(notification)
    db.commit()
    db.refresh(notification)

    employee = db.get(Employee, employee_id)
    if employee is not None:
        send_email_hook(employee, message)
    return notification


def mark_read(notification: Notification) -> None:
    notification.IsRead = True


def _employees_with_role(db: Session, role_code: str, plant_id: int | None = None) -> list[Employee]:
    query = (
        db.query(Employee)
        .join(User, User.EmployeeID == Employee.EmployeeID)
        .join(UserRole, UserRole.UserID == User.UserID)
        .join(Role, Role.RoleID == UserRole.RoleID)
        .filter(
            Role.RoleCode == role_code,
            User.IsActive == True,  # noqa: E712
            Employee.IsActive == True,  # noqa: E712
        )
    )
    if plant_id is not None:
        query = query.filter(Employee.PlantID == plant_id)
    return query.all()


def resolve_recipients(db: Session, performance: EmployeePerformance) -> list[Employee]:
    """See module docstring's "DESIGN NOTE on recipients"."""
    kind = STAGE_RECIPIENT_KIND.get(performance.Status)
    if kind is None:
        return []
    employee = performance.employee
    if kind == "SELF":
        return [employee]
    if kind == "MANAGER":
        return [employee.manager] if employee.manager is not None else []
    if kind == "HOD":
        return [employee.hod] if employee.hod is not None else []
    if kind == "HR":
        if employee.hr_contact is not None:
            return [employee.hr_contact]
        return _employees_with_role(db, "HR")
    if kind == "PLANT_HEAD":
        return _employees_with_role(db, "PLANT_HEAD", plant_id=employee.PlantID)
    if kind == "MD":
        return _employees_with_role(db, "MD")
    return []


def notify_stage_transition(db: Session, performance: EmployeePerformance) -> list[Notification]:
    """Called immediately after record_transition() at every existing
    transition call site - see module docstring."""
    recipients = resolve_recipients(db, performance)
    message = STAGE_MESSAGE.get(
        performance.Status, f"Your appraisal status changed to {performance.Status}.",
    )
    return [
        create_notification(db, employee_id=recipient.EmployeeID, message=message, module="WORKFLOW")
        for recipient in recipients
    ]
