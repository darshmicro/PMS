"""
Tests run against an in-memory SQLite DB (not SQL Server) purely to
validate ORM relationships and service-layer logic quickly and without
external dependencies. Section 47's test cases (valid/invalid AD user,
inactive employee, unauthorized role) are implemented against this fixture.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.assignment import EmployeeKPA, EmployeeKPI, EmployeePerformance  # noqa: F401
from app.models.self_assessment import SelfAssessment  # noqa: F401
from app.models.manager_review import ManagerReview  # noqa: F401
from app.models.hod_review import HODReview  # noqa: F401
from app.models.hr_review import HRReview  # noqa: F401
from app.models.plant_head_approval import PlantHeadApproval  # noqa: F401
from app.models.md_approval import MDApproval  # noqa: F401
from app.models.employee_competency import EmployeeCompetency  # noqa: F401
from app.models.performance_score import PerformanceRating, PerformanceScore  # noqa: F401
from app.models.workflow_history import WorkflowHistory  # noqa: F401
from app.models.development_plan import DevelopmentPlan  # noqa: F401
from app.models.pip import PIP  # noqa: F401
from app.models.attachment import Attachment  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.system_config import SystemConfig  # noqa: F401
from app.models.demo_credential import DemoCredential  # noqa: F401
from app.models.employee import Employee
from app.models.masters import Company, Department, Designation, EmployeeCategory, Grade, Plant, Section  # noqa: F401
from app.models.performance_masters import (  # noqa: F401
    CompetencyMaster,
    KPAMaster,
    KPIMaster,
    KPIScoringRule,
    PerformanceCycle,
    RatingMaster,
)
from app.models.rbac import Permission, Role, RolePermission, User, UserRole


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def seeded_db(db_session):
    role_employee = Role(RoleCode="EMPLOYEE", RoleName="Employee", IsBusinessRole=True, IsActive=True)
    role_hod = Role(RoleCode="HOD", RoleName="Head of Department", IsBusinessRole=True, IsActive=True)
    role_sysadmin = Role(RoleCode="SYS_ADMIN", RoleName="System Administrator", IsBusinessRole=False, IsActive=True)
    db_session.add_all([role_employee, role_hod, role_sysadmin])
    db_session.flush()

    perm_view = Permission(PermissionCode="MASTERS.VIEW", Module="MASTERS", Description="View masters")
    perm_edit = Permission(PermissionCode="MASTERS.EDIT", Module="MASTERS", Description="Edit masters")
    db_session.add_all([perm_view, perm_edit])
    db_session.flush()

    db_session.add(RolePermission(RoleID=role_hod.RoleID, PermissionID=perm_view.PermissionID))
    db_session.add(RolePermission(RoleID=role_hod.RoleID, PermissionID=perm_edit.PermissionID))

    active_employee = Employee(
        EmployeeCode="EMP0001", ADUsername="COMPANY\\active_user", FullName="Active User",
        EmploymentStatus="ACTIVE", IsActive=True,
    )
    inactive_employee = Employee(
        EmployeeCode="EMP0002", ADUsername="COMPANY\\inactive_user", FullName="Inactive User",
        EmploymentStatus="INACTIVE", IsActive=False,
    )
    db_session.add_all([active_employee, inactive_employee])
    db_session.flush()

    active_user = User(ADUsername="COMPANY\\active_user", EmployeeID=active_employee.EmployeeID, IsActive=True)
    inactive_employee_user = User(
        ADUsername="COMPANY\\inactive_user", EmployeeID=inactive_employee.EmployeeID, IsActive=True
    )
    deactivated_account_user = User(ADUsername="COMPANY\\deactivated_account", IsActive=False)
    no_role_user = User(ADUsername="COMPANY\\no_role_user", IsActive=True)

    db_session.add_all(
        [active_user, inactive_employee_user, deactivated_account_user, no_role_user]
    )
    db_session.flush()

    db_session.add(UserRole(UserID=active_user.UserID, RoleID=role_hod.RoleID))
    db_session.commit()

    return db_session
