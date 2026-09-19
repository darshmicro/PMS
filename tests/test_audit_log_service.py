from dataclasses import dataclass

from app.models.audit import AuditLog
from app.models.employee import Employee
from app.services.audit_log_service import SCOPE_ALL, SCOPE_DEPT, SCOPE_PLANT, apply_audit_scope


@dataclass
class _Ctx:
    employee_id: int | None
    role_codes: list[str]


def _seed(db_session):
    hr = Employee(EmployeeCode="AUD-HR", ADUsername="COMPANY\\audhr", FullName="Audit HR", DepartmentID=1)
    plant_head = Employee(EmployeeCode="AUD-PH", ADUsername="COMPANY\\audph", FullName="Audit Plant Head", PlantID=1)
    same_dept = Employee(EmployeeCode="AUD-SAMEDEPT", ADUsername="COMPANY\\audsd", FullName="Same Dept", DepartmentID=1)
    other_dept = Employee(EmployeeCode="AUD-OTHERDEPT", ADUsername="COMPANY\\audod", FullName="Other Dept", DepartmentID=2)
    same_plant = Employee(EmployeeCode="AUD-SAMEPLANT", ADUsername="COMPANY\\audsp", FullName="Same Plant", PlantID=1)
    other_plant = Employee(EmployeeCode="AUD-OTHERPLANT", ADUsername="COMPANY\\audop", FullName="Other Plant", PlantID=2)
    db_session.add_all([hr, plant_head, same_dept, other_dept, same_plant, other_plant])
    db_session.flush()

    db_session.add_all([
        AuditLog(Action="EDIT", Module="TEST", EmployeeID=same_dept.EmployeeID),
        AuditLog(Action="EDIT", Module="TEST", EmployeeID=other_dept.EmployeeID),
        AuditLog(Action="EDIT", Module="TEST", EmployeeID=same_plant.EmployeeID),
        AuditLog(Action="EDIT", Module="TEST", EmployeeID=other_plant.EmployeeID),
        AuditLog(Action="LOGIN", Module="AUTH", EmployeeID=None),
    ])
    db_session.commit()
    return {"hr": hr, "plant_head": plant_head, "same_dept": same_dept, "same_plant": same_plant}


def test_hr_is_department_scoped(db_session):
    ids = _seed(db_session)
    query, scope = apply_audit_scope(
        db_session.query(AuditLog), db_session, _Ctx(employee_id=ids["hr"].EmployeeID, role_codes=["HR"]),
    )
    assert scope == SCOPE_DEPT
    rows = query.all()
    assert len(rows) == 1
    assert rows[0].EmployeeID == ids["same_dept"].EmployeeID


def test_plant_head_is_plant_scoped(db_session):
    ids = _seed(db_session)
    query, scope = apply_audit_scope(
        db_session.query(AuditLog), db_session, _Ctx(employee_id=ids["plant_head"].EmployeeID, role_codes=["PLANT_HEAD"]),
    )
    assert scope == SCOPE_PLANT
    rows = query.all()
    assert len(rows) == 1
    assert rows[0].EmployeeID == ids["same_plant"].EmployeeID


def test_md_sees_everything_including_employeeless_rows(db_session):
    _seed(db_session)
    query, scope = apply_audit_scope(db_session.query(AuditLog), db_session, _Ctx(employee_id=999, role_codes=["MD"]))
    assert scope == SCOPE_ALL
    assert query.count() == 5


def test_hr_admin_sees_everything(db_session):
    _seed(db_session)
    query, scope = apply_audit_scope(db_session.query(AuditLog), db_session, _Ctx(employee_id=999, role_codes=["HR_ADMIN"]))
    assert scope == SCOPE_ALL
    assert query.count() == 5


def test_sys_admin_sees_everything(db_session):
    _seed(db_session)
    query, scope = apply_audit_scope(db_session.query(AuditLog), db_session, _Ctx(employee_id=None, role_codes=["SYS_ADMIN"]))
    assert scope == SCOPE_ALL
    assert query.count() == 5


def test_hr_with_no_department_sees_nothing(db_session):
    hr_no_dept = Employee(EmployeeCode="AUD-HR2", ADUsername="COMPANY\\audhr2", FullName="HR No Dept")
    db_session.add(hr_no_dept)
    db_session.flush()
    db_session.add(AuditLog(Action="EDIT", Module="TEST", EmployeeID=hr_no_dept.EmployeeID))
    db_session.commit()

    query, scope = apply_audit_scope(
        db_session.query(AuditLog), db_session, _Ctx(employee_id=hr_no_dept.EmployeeID, role_codes=["HR"]),
    )
    assert scope == SCOPE_DEPT
    assert query.count() == 0
