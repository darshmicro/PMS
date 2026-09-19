from app.api.routes.employees import _apply_scope
from app.core.dependencies import CurrentContext
from app.models.employee import Employee


def _ctx(role_codes, employee_id=1):
    return CurrentContext(
        user_id=employee_id, ad_username="COMPANY\\u", employee_id=employee_id,
        role_codes=role_codes, permission_codes=set(),
    )


def _seed_org(db_session):
    manager = Employee(EmployeeCode="MGR001", ADUsername="COMPANY\\mgr", FullName="Manager One")
    hod = Employee(EmployeeCode="HOD001", ADUsername="COMPANY\\hod", FullName="HOD One")
    db_session.add_all([manager, hod])
    db_session.flush()

    report1 = Employee(
        EmployeeCode="EMP101", ADUsername="COMPANY\\e101", FullName="Report One",
        ManagerID=manager.EmployeeID, HODID=hod.EmployeeID,
    )
    report2 = Employee(
        EmployeeCode="EMP102", ADUsername="COMPANY\\e102", FullName="Report Two",
        ManagerID=manager.EmployeeID, HODID=hod.EmployeeID,
    )
    other = Employee(EmployeeCode="EMP999", ADUsername="COMPANY\\e999", FullName="Unrelated Employee")
    db_session.add_all([report1, report2, other])
    db_session.commit()
    return manager, hod, report1, report2, other


def test_broad_role_sees_all_employees(db_session):
    manager, hod, r1, r2, other = _seed_org(db_session)
    ctx = _ctx(["HR"], employee_id=manager.EmployeeID)
    result = _apply_scope(db_session.query(Employee), ctx, db_session).all()
    assert len(result) == 5  # manager, hod, r1, r2, other


def test_manager_role_sees_only_direct_reports(db_session):
    manager, hod, r1, r2, other = _seed_org(db_session)
    ctx = _ctx(["MANAGER"], employee_id=manager.EmployeeID)
    result = _apply_scope(db_session.query(Employee), ctx, db_session).all()
    codes = {e.EmployeeCode for e in result}
    assert codes == {"EMP101", "EMP102"}


def test_hod_role_sees_only_department_employees(db_session):
    manager, hod, r1, r2, other = _seed_org(db_session)
    ctx = _ctx(["HOD"], employee_id=hod.EmployeeID)
    result = _apply_scope(db_session.query(Employee), ctx, db_session).all()
    codes = {e.EmployeeCode for e in result}
    assert codes == {"EMP101", "EMP102"}


def test_plain_employee_role_sees_only_self(db_session):
    manager, hod, r1, r2, other = _seed_org(db_session)
    ctx = _ctx(["EMPLOYEE"], employee_id=r1.EmployeeID)
    result = _apply_scope(db_session.query(Employee), ctx, db_session).all()
    assert [e.EmployeeCode for e in result] == ["EMP101"]
