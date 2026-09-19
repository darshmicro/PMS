"""
Server-issued, signed session cookie. Deliberately minimal: it carries only
`user_id` + `issued_at`. Roles/permissions are NEVER cached in the cookie -
they are re-read from the DB on every request, so a permission change or
deactivation takes effect immediately rather than only after next login.
"""
from datetime import datetime, timedelta, timezone

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import get_settings

settings = get_settings()
_serializer = URLSafeTimedSerializer(settings.SESSION_SECRET_KEY, salt="pms-session")

SESSION_COOKIE_NAME = "pms_session"


def create_session_token(user_id: int) -> str:
    return _serializer.dumps({"user_id": user_id, "issued_at": datetime.now(timezone.utc).isoformat()})


def read_session_token(token: str) -> int | None:
    """Returns user_id if the token is valid and within the idle timeout, else None."""
    max_age_seconds = settings.SESSION_TIMEOUT_MINUTES * 60
    try:
        data = _serializer.loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id")


def session_cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "samesite": "strict",
        "secure": settings.ENVIRONMENT == "production",
        "max_age": settings.SESSION_TIMEOUT_MINUTES * 60,
    }
