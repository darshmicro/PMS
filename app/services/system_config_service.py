"""
System Configuration business rules (spec Section 5 row 545 / M28). See
the model's docstring for the full reasoning behind NON_SECRET_KEYS -
this allowlist is the enforcement point: it is what stops System_Config
from ever becoming a plaintext store for credentials that belong in
environment variables only (SESSION_SECRET_KEY, DB_PASSWORD,
AD_BIND_PASSWORD, etc. - see app/core/config.py's own Settings class).
"""
import re

from sqlalchemy.orm import Session

from app.models.system_config import SystemConfig

# Exactly the settings the matrix row names by example ("SMTP, AD server,
# storage path") plus their natural companion fields. Anything else is
# rejected by is_secret_like() below, key allowlist first, pattern second.
NON_SECRET_KEYS = frozenset({
    "SMTP_SERVER", "SMTP_PORT", "SMTP_FROM",
    "AD_SERVER", "AD_DOMAIN",
    "FILE_STORAGE_PATH", "MAX_UPLOAD_SIZE_MB",
})

# Defence in depth even for a key theoretically added to NON_SECRET_KEYS
# later: nothing whose name looks like a credential is ever accepted.
_SECRET_PATTERN = re.compile(r"(PASSWORD|SECRET|TOKEN|BIND_DN|API_KEY)", re.IGNORECASE)


class ConfigKeyRejected(ValueError):
    """Raised when a config key is not in the non-secret allowlist."""


def is_secret_like(key: str) -> bool:
    return bool(_SECRET_PATTERN.search(key))


def validate_key(key: str) -> None:
    if is_secret_like(key):
        raise ConfigKeyRejected(
            f"'{key}' looks like a credential and can never be stored in System_Config - "
            "secrets belong in environment variables only."
        )
    if key not in NON_SECRET_KEYS:
        raise ConfigKeyRejected(
            f"'{key}' is not a recognised system configuration key. Allowed keys: "
            f"{sorted(NON_SECRET_KEYS)}"
        )


def list_config(db: Session) -> list[SystemConfig]:
    return db.query(SystemConfig).order_by(SystemConfig.ConfigKey.asc()).all()


def get_config(db: Session, key: str) -> SystemConfig | None:
    return db.query(SystemConfig).filter(SystemConfig.ConfigKey == key).one_or_none()


def upsert_config(
    db: Session, *, key: str, value: str | None, description: str | None, modified_by: int | None,
) -> SystemConfig:
    """Validates the key, then creates or updates the row - a single entry
    point for both POST (create) and PUT (edit), since the business rule
    (only these keys, ever) is identical either way."""
    validate_key(key)
    existing = get_config(db, key)
    if existing is not None:
        existing.ConfigValue = value
        if description is not None:
            existing.Description = description
        existing.ModifiedBy = modified_by
        db.commit()
        db.refresh(existing)
        return existing

    row = SystemConfig(ConfigKey=key, ConfigValue=value, Description=description, ModifiedBy=modified_by)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
