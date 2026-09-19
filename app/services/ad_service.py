"""
Active Directory integration (spec Section 5).

Two supported modes, controlled by settings.AUTH_MODE:

1. "iis_forwarded" (recommended for production):
   IIS sits in front of this app with Windows Authentication enabled and
   Kerberos/NTLM configured for the intranet zone. IIS performs the actual
   domain handshake and forwards the authenticated Windows identity to the
   app as a request header (e.g. X-Remote-User: COMPANY\\jdoe), set via the
   IIS URL Rewrite / ARR reverse-proxy rule. The app NEVER sees a password
   in this mode - it only trusts the header, and only because the network
   path from IIS to the app is restricted to localhost/loopback.

2. "ldap_bind" (dev/testing, or intranet segments without IIS in front):
   The user submits DOMAIN\\username + password to /auth/login. The app
   binds to AD over LDAPS with those credentials purely to verify them,
   then immediately discards the password - it is never stored, logged,
   or cached.

Both modes converge on the same output: a verified AD username, which
auth_service.py then maps to an Employee/User record.
"""
from dataclasses import dataclass

from ldap3 import ALL, NTLM, SUBTREE, Connection, Server

from app.core.config import get_settings

settings = get_settings()


@dataclass
class ADUserInfo:
    ad_username: str          # normalized DOMAIN\username
    display_name: str | None
    email: str | None


class ADAuthError(Exception):
    pass


def _normalize_username(raw: str) -> str:
    """Accepts 'DOMAIN\\user', 'user@domain.local', or bare 'user' and
    normalizes to 'DOMAIN\\user' for consistent lookup against Users.ADUsername."""
    raw = raw.strip()
    if "\\" in raw:
        return raw
    if "@" in raw:
        user_part = raw.split("@")[0]
        return f"{settings.AD_DOMAIN}\\{user_part}"
    return f"{settings.AD_DOMAIN}\\{raw}"


def authenticate_via_ldap_bind(username: str, password: str) -> ADUserInfo:
    """
    Mode 2: verify credentials by attempting an NTLM bind to AD.
    Raises ADAuthError on any failure (bad password, disabled account, AD unreachable).
    The password is used only for this bind call and is never persisted.
    """
    normalized = _normalize_username(username)
    server = Server(settings.AD_SERVER, port=settings.AD_PORT, use_ssl=settings.AD_USE_SSL, get_info=ALL)

    try:
        conn = Connection(server, user=normalized, password=password, authentication=NTLM, auto_bind=True)
    except Exception as exc:  # noqa: BLE001 - AD/LDAP libs raise broad exceptions
        raise ADAuthError("Invalid credentials or AD unreachable") from exc

    try:
        search_filter = f"(sAMAccountName={normalized.split(chr(92))[-1]})"
        conn.search(
            search_base=settings.AD_BASE_DN,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=["displayName", "mail", "userAccountControl"],
        )
        if not conn.entries:
            raise ADAuthError("User authenticated but not found in AD directory")

        entry = conn.entries[0]
        uac = int(entry.userAccountControl.value) if "userAccountControl" in entry else 0
        ACCOUNTDISABLE = 0x0002
        if uac & ACCOUNTDISABLE:
            raise ADAuthError("AD account is disabled")

        return ADUserInfo(
            ad_username=normalized,
            display_name=str(entry.displayName.value) if "displayName" in entry else None,
            email=str(entry.mail.value) if "mail" in entry else None,
        )
    finally:
        conn.unbind()


def authenticate_via_iis_header(header_value: str | None) -> ADUserInfo:
    """
    Mode 1: trust the identity IIS already verified via Windows Auth/Kerberos.
    header_value looks like "COMPANY\\jdoe" (IIS LOGON_USER / REMOTE_USER passed through).
    """
    if not header_value:
        raise ADAuthError("No authenticated Windows identity was forwarded by IIS")
    return ADUserInfo(ad_username=_normalize_username(header_value), display_name=None, email=None)
