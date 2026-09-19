import pytest

from app.models.demo_credential import DemoCredential
from app.models.rbac import User
from app.services.ad_service import ADAuthError
from app.services.demo_auth_service import (
    authenticate_demo_login,
    change_own_password,
    hash_password,
    set_password,
    verify_password,
)


def test_hash_and_verify_roundtrip():
    hashed = hash_password("correct-horse-battery")
    assert hashed != "correct-horse-battery"
    assert verify_password("correct-horse-battery", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_hash_password_rejects_short_password():
    with pytest.raises(ValueError):
        hash_password("short")


def _seed_user(db_session, username="demoadmin"):
    user = User(ADUsername=username, IsActive=True)
    db_session.add(user)
    db_session.flush()
    db_session.commit()
    return user


def test_authenticate_demo_login_succeeds_with_correct_password(db_session):
    user = _seed_user(db_session)
    set_password(db_session, user.UserID, "correct-horse-battery")
    resolved = authenticate_demo_login(db_session, "demoadmin", "correct-horse-battery")
    assert resolved == "demoadmin"


def test_authenticate_demo_login_fails_with_wrong_password(db_session):
    user = _seed_user(db_session)
    set_password(db_session, user.UserID, "correct-horse-battery")
    with pytest.raises(ADAuthError):
        authenticate_demo_login(db_session, "demoadmin", "wrong-password")


def test_authenticate_demo_login_fails_for_unknown_username(db_session):
    with pytest.raises(ADAuthError):
        authenticate_demo_login(db_session, "nobody", "whatever123")


def test_authenticate_demo_login_fails_when_no_credential_set(db_session):
    _seed_user(db_session)
    with pytest.raises(ADAuthError):
        authenticate_demo_login(db_session, "demoadmin", "whatever123")


def test_set_password_creates_then_updates(db_session):
    user = _seed_user(db_session)
    set_password(db_session, user.UserID, "first-password")
    assert db_session.query(DemoCredential).filter(DemoCredential.UserID == user.UserID).count() == 1

    set_password(db_session, user.UserID, "second-password")
    assert db_session.query(DemoCredential).filter(DemoCredential.UserID == user.UserID).count() == 1
    assert authenticate_demo_login(db_session, "demoadmin", "second-password") == "demoadmin"


def test_change_own_password_requires_correct_current_password(db_session):
    user = _seed_user(db_session)
    set_password(db_session, user.UserID, "first-password")

    with pytest.raises(ADAuthError):
        change_own_password(db_session, user.UserID, "wrong-current", "new-password-1")

    change_own_password(db_session, user.UserID, "first-password", "new-password-1")
    assert authenticate_demo_login(db_session, "demoadmin", "new-password-1") == "demoadmin"
