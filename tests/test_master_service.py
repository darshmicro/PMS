import pytest
from fastapi import HTTPException

from app.core.dependencies import CurrentContext
from app.models.audit import AuditLog
from app.models.masters import Designation
from app.services import master_service as ms

DESIGNATION_CFG = ms.MasterFieldConfig(
    Designation, "DesignationID", "DesignationCode", "DesignationName", "MASTERS.DESIGNATION"
)


@pytest.fixture()
def fake_ctx():
    return CurrentContext(
        user_id=1, ad_username="COMPANY\\hr_admin", employee_id=1,
        role_codes=["HR_ADMIN"], permission_codes={"MASTERS.EDIT", "MASTERS.VIEW", "MASTERS.DEACTIVATE"},
    )


def test_create_master_record_succeeds_and_writes_audit(db_session, fake_ctx):
    data = {"DesignationCode": "DSG-001", "DesignationName": "Executive"}
    instance = ms.create_record(db_session, DESIGNATION_CFG, data, fake_ctx, "10.0.0.5")

    assert instance.DesignationID is not None
    assert instance.IsActive is True

    audit_rows = db_session.query(AuditLog).filter(AuditLog.Module == "MASTERS.DESIGNATION").all()
    assert len(audit_rows) == 1
    assert audit_rows[0].Action == "CREATE"
    assert audit_rows[0].IPAddress == "10.0.0.5"


def test_duplicate_code_is_rejected(db_session, fake_ctx):
    data = {"DesignationCode": "DSG-002", "DesignationName": "Manager"}
    ms.create_record(db_session, DESIGNATION_CFG, data, fake_ctx, None)

    with pytest.raises(HTTPException) as exc_info:
        ms.create_record(db_session, DESIGNATION_CFG, data, fake_ctx, None)
    assert exc_info.value.status_code == 409


def test_update_master_record_writes_old_and_new_value_to_audit(db_session, fake_ctx):
    instance = ms.create_record(
        db_session, DESIGNATION_CFG, {"DesignationCode": "DSG-003", "DesignationName": "Senior Manager"},
        fake_ctx, None,
    )
    updated = ms.update_record(
        db_session, DESIGNATION_CFG, instance.DesignationID,
        {"DesignationName": "Senior Manager II"}, fake_ctx, None,
    )
    assert updated.DesignationName == "Senior Manager II"

    audit_rows = db_session.query(AuditLog).filter(
        AuditLog.Module == "MASTERS.DESIGNATION", AuditLog.Action == "EDIT"
    ).all()
    assert len(audit_rows) == 1
    assert "Senior Manager" in audit_rows[0].OldValue
    assert "Senior Manager II" in audit_rows[0].NewValue


def test_deactivate_requires_no_hard_delete_and_records_reason(db_session, fake_ctx):
    instance = ms.create_record(
        db_session, DESIGNATION_CFG, {"DesignationCode": "DSG-004", "DesignationName": "Trainee"},
        fake_ctx, None,
    )
    deactivated = ms.set_active_status(
        db_session, DESIGNATION_CFG, instance.DesignationID, False, "Role discontinued", fake_ctx, None,
    )
    assert deactivated.IsActive is False
    # record still exists - no hard delete (spec Section 6/35)
    assert ms.get_record(db_session, DESIGNATION_CFG, instance.DesignationID) is not None

    audit_row = db_session.query(AuditLog).filter(AuditLog.Action == "DEACTIVATE").one()
    assert audit_row.Reason == "Role discontinued"


def test_get_nonexistent_record_returns_404(db_session):
    with pytest.raises(HTTPException) as exc_info:
        ms.get_record(db_session, DESIGNATION_CFG, 99999)
    assert exc_info.value.status_code == 404
