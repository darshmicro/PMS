import pytest

from app.services.system_config_service import (
    ConfigKeyRejected,
    get_config,
    is_secret_like,
    list_config,
    upsert_config,
    validate_key,
)


def test_non_secret_key_passes_validation():
    validate_key("SMTP_SERVER")  # no raise


@pytest.mark.parametrize("key", ["DB_PASSWORD", "AD_BIND_PASSWORD", "SESSION_SECRET_KEY", "some_api_key", "AD_BIND_DN"])
def test_secret_like_keys_are_rejected(key):
    assert is_secret_like(key) is True
    with pytest.raises(ConfigKeyRejected):
        validate_key(key)


def test_unknown_non_secret_key_is_also_rejected():
    with pytest.raises(ConfigKeyRejected):
        validate_key("SOME_RANDOM_SETTING")


def test_upsert_creates_then_updates(db_session):
    row = upsert_config(db_session, key="FILE_STORAGE_PATH", value="/mnt/attachments", description="Storage root", modified_by=None)
    assert row.ConfigID is not None
    assert row.ConfigValue == "/mnt/attachments"

    updated = upsert_config(db_session, key="FILE_STORAGE_PATH", value="/mnt/attachments-v2", description=None, modified_by=None)
    assert updated.ConfigID == row.ConfigID
    assert updated.ConfigValue == "/mnt/attachments-v2"
    # Description is preserved when not supplied on update.
    assert updated.Description == "Storage root"

    assert len(list_config(db_session)) == 1
    assert get_config(db_session, "FILE_STORAGE_PATH").ConfigValue == "/mnt/attachments-v2"


def test_upsert_rejects_secret_key(db_session):
    with pytest.raises(ConfigKeyRejected):
        upsert_config(db_session, key="AD_BIND_PASSWORD", value="hunter2", description=None, modified_by=None)
    assert list_config(db_session) == []


def test_get_config_missing_returns_none(db_session):
    assert get_config(db_session, "SMTP_SERVER") is None
