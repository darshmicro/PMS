from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.notification import Notification
from app.models.rbac import Role, User, UserRole
from app.services.notification_service import (
    STAGE_MESSAGE,
    STAGE_RECIPIENT_KIND,
    create_notification,
    mark_read,
    notify_stage_transition,
    resolve_recipients,
    send_email_hook,
)


def _seed_basic_chain(db_session):
    hod = Employee(EmployeeCode="HOD1", ADUsername="COMPANY\\hod1", FullName="Hod One")
    manager = Employee(EmployeeCode="MGR1", ADUsername="COMPANY\\mgr1", FullName="Manager One")
    hr_contact = Employee(EmployeeCode="HR1", ADUsername="COMPANY\\hr1", FullName="HR Contact One")
    db_session.add_all([hod, manager, hr_contact])
    db_session.flush()

    employee = Employee(
        EmployeeCode="EMP1", ADUsername="COMPANY\\emp1", FullName="Employee One",
        ManagerID=manager.EmployeeID, HODID=hod.EmployeeID, HRID=hr_contact.EmployeeID,
    )
    db_session.add(employee)
    db_session.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=1, Status="MANAGER_REVIEW")
    db_session.add(performance)
    db_session.commit()
    return employee, manager, hod, hr_contact, performance


def test_resolve_recipients_self(db_session):
    employee, _, _, _, performance = _seed_basic_chain(db_session)
    performance.Status = "EMPLOYEE_ACKNOWLEDGED"
    recipients = resolve_recipients(db_session, performance)
    assert [r.EmployeeID for r in recipients] == [employee.EmployeeID]


def test_resolve_recipients_manager(db_session):
    _, manager, _, _, performance = _seed_basic_chain(db_session)
    performance.Status = "MANAGER_REVIEW"
    recipients = resolve_recipients(db_session, performance)
    assert [r.EmployeeID for r in recipients] == [manager.EmployeeID]


def test_resolve_recipients_hod(db_session):
    _, _, hod, _, performance = _seed_basic_chain(db_session)
    performance.Status = "HOD_REVIEW"
    recipients = resolve_recipients(db_session, performance)
    assert [r.EmployeeID for r in recipients] == [hod.EmployeeID]


def test_resolve_recipients_hr_prefers_hr_contact(db_session):
    _, _, _, hr_contact, performance = _seed_basic_chain(db_session)
    performance.Status = "HR_REVIEW"
    recipients = resolve_recipients(db_session, performance)
    assert [r.EmployeeID for r in recipients] == [hr_contact.EmployeeID]


def test_resolve_recipients_hr_falls_back_to_role_when_no_hr_contact(db_session):
    employee = Employee(EmployeeCode="EMP2", ADUsername="COMPANY\\emp2", FullName="Employee Two")
    hr_user_employee = Employee(EmployeeCode="HRROLE1", ADUsername="COMPANY\\hrrole1", FullName="HR Role Holder")
    db_session.add_all([employee, hr_user_employee])
    db_session.flush()

    role = Role(RoleCode="HR", RoleName="HR")
    db_session.add(role)
    db_session.flush()
    user = User(ADUsername="COMPANY\\hrrole1", EmployeeID=hr_user_employee.EmployeeID, IsActive=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(UserID=user.UserID, RoleID=role.RoleID))
    db_session.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=1, Status="HR_REVIEW")
    db_session.add(performance)
    db_session.commit()

    recipients = resolve_recipients(db_session, performance)
    assert [r.EmployeeID for r in recipients] == [hr_user_employee.EmployeeID]


def test_resolve_recipients_unmapped_status_returns_empty(db_session):
    employee, _, _, _, performance = _seed_basic_chain(db_session)
    performance.Status = "DRAFT"
    assert resolve_recipients(db_session, performance) == []


def test_resolve_recipients_missing_manager_returns_empty(db_session):
    employee = Employee(EmployeeCode="EMP3", ADUsername="COMPANY\\emp3", FullName="Employee Three")
    db_session.add(employee)
    db_session.flush()
    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=1, Status="MANAGER_REVIEW")
    db_session.add(performance)
    db_session.commit()
    assert resolve_recipients(db_session, performance) == []


def test_create_notification_writes_a_row(db_session):
    employee = Employee(EmployeeCode="EMP4", ADUsername="COMPANY\\emp4", FullName="Employee Four")
    db_session.add(employee)
    db_session.commit()

    notification = create_notification(db_session, employee_id=employee.EmployeeID, message="Hello", module="TEST")
    assert notification.NotificationID is not None
    assert notification.IsRead is False
    fetched = db_session.get(Notification, notification.NotificationID)
    assert fetched.Message == "Hello"


def test_mark_read_sets_flag():
    notification = Notification(EmployeeID=1, Message="x", IsRead=False)
    assert notification.IsRead is False
    mark_read(notification)
    assert notification.IsRead is True


def test_send_email_hook_is_a_documented_noop(db_session):
    employee = Employee(EmployeeCode="EMP5", ADUsername="COMPANY\\emp5", FullName="Employee Five")
    assert send_email_hook(employee, "hi") is None


def test_notify_stage_transition_creates_one_row_per_recipient(db_session):
    employee, manager, _, _, performance = _seed_basic_chain(db_session)
    created = notify_stage_transition(db_session, performance)
    assert len(created) == 1
    assert created[0].EmployeeID == manager.EmployeeID
    assert created[0].Message == STAGE_MESSAGE["MANAGER_REVIEW"]


def test_every_stage_recipient_kind_maps_to_a_message():
    assert set(STAGE_RECIPIENT_KIND.keys()) == set(STAGE_MESSAGE.keys())
