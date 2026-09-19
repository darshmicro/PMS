"""
Local (non-AD) password authentication against the app's own Demo_Login
table (bcrypt-hashed via passlib). Despite the module/table name -
"Demo_Login" predates this - it backs two different AUTH_MODE values:

1. demo_local: the ONLY auth path, for a Windows 11 Home machine with no
   Active Directory domain to join and no IIS Windows-Integrated-Auth/
   Kerberos available - a local proof-of-concept/demo deployment.
   app/api/routes/auth.py refuses this mode outright when
   settings.ENVIRONMENT == "production": it intentionally provides none
   of AD's protections (account lockout policy, password complexity
   enforcement, centralized deactivation, Kerberos SSO, domain audit), so
   it must never become the ONLY auth path for a real deployment.

2. hybrid: this module runs ALONGSIDE ad_service.py's ldap_bind, not
   instead of it - see login()'s "hybrid" branch in
   app/api/routes/auth.py. Every login attempt is checked against this
   table first (find_local_login); if no local account matches, the
   attempt falls through to an AD bind. This is what lets one company
   intranet deployment serve both real AD users (SSO-style username/
   password checked live against the domain) and local, non-AD accounts
   (contractors, a break-glass admin for when the domain controller is
   unreachable) from the same login screen, and IS permitted in
   production - see DEPLOYMENT.md's "Hybrid (AD + local users)" section.

DESIGN NOTE on why this is a real, separate module rather than a
workaround inside ad_service.py: ad_service.py's two modes
(iis_forwarded, ldap_bind) both ultimately verify an identity *against
AD*. A local account has no AD entry to verify against by definition, so
neither mode applies. This module reuses ad_service.ADAuthError as its
own exception type purely so app/api/routes/auth.py's existing
try/except in the login route needs no change in shape - not because
this has anything to do with AD.
"""
from sqlalchemy.orm import Session

from app.models.demo_credential import DemoCredential
from app.models.rbac import User
from app.services.ad_service import ADAuthError, _normalize_username

try:
    from passlib.context import CryptContext
    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
except ImportError:  # pragma: no cover - passlib is in requirements.txt
    _pwd_context = None


def hash_password(plain_password: str) -> str:
    if len(plain_password) < 8:
        raise ValueError("Password must be at least 8 characters")
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return _pwd_context.verify(plain_password, password_hash)


def find_local_login(db: Session, raw_username: str) -> User | None:
    """AUTH_MODE=hybrid helper (see module docstring, point 2): does a
    local, Demo_Login-backed account exist for this raw login string?
    Tried both exactly as typed and in the normalized DOMAIN\\username
    form ad_service.py uses for AD lookups - a local-only account
    commonly uses a distinct, non-AD prefix (e.g. "LOCAL\\contractor1" or
    a bare "svc_reports") rather than the real AD domain, so a bare
    "contractor1" must not be silently coerced into "COMPANY\\contractor1"
    before this check runs. Returns None (not an error) when nothing
    local matches - the hybrid login route then falls through to an AD
    bind, since an unrecognized username here just means "not a local
    account", not "invalid credentials"."""
    raw = raw_username.strip()
    candidates = {raw}
    try:
        candidates.add(_normalize_username(raw))
    except Exception:  # noqa: BLE001 - normalization is best-effort here
        pass
    return (
        db.query(User)
        .join(DemoCredential, DemoCredential.UserID == User.UserID)
        .filter(User.ADUsername.in_(candidates))
        .one_or_none()
    )


def authenticate_demo_login(db: Session, username: str, password: str) -> str:
    """Returns the matched Users.ADUsername (reused as the demo login
    username field - see model docstring) on success. Raises ADAuthError
    on any failure, deliberately generic (no "wrong password" vs
    "unknown user" distinction), matching ldap_bind's own never-reveal
    convention (spec Section 45)."""
    user = db.query(User).filter(User.ADUsername == username).one_or_none()
    if user is None:
        raise ADAuthError("Invalid credentials")

    credential = db.query(DemoCredential).filter(DemoCredential.UserID == user.UserID).one_or_none()
    if credential is None or not verify_password(password, credential.PasswordHash):
        raise ADAuthError("Invalid credentials")

    return user.ADUsername


def set_password(db: Session, user_id: int, new_password: str) -> None:
    """Admin reset or first-time set - no current-password check. Used by
    POST /auth/demo/set-password/{user_id} (HR_ADMIN/SYS_ADMIN only)."""
    new_hash = hash_password(new_password)
    existing = db.query(DemoCredential).filter(DemoCredential.UserID == user_id).one_or_none()
    if existing is not None:
        existing.PasswordHash = new_hash
    else:
        db.add(DemoCredential(UserID=user_id, PasswordHash=new_hash))
    db.commit()


def change_own_password(db: Session, user_id: int, current_password: str, new_password: str) -> None:
    """Self-service - requires knowing the current password. Used by
    PUT /auth/demo/change-password."""
    credential = db.query(DemoCredential).filter(DemoCredential.UserID == user_id).one_or_none()
    if credential is None or not verify_password(current_password, credential.PasswordHash):
        raise ADAuthError("Current password is incorrect")
    credential.PasswordHash = hash_password(new_password)
    db.commit()
