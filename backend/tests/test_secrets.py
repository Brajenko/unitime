from datetime import datetime, timedelta, timezone

from app.security import secret_box


def test_secret_roundtrip():
    payload = {"access_token": "abc", "refresh_token": "def", "expires_at": datetime.now(timezone.utc).isoformat()}
    blob = secret_box.encrypt(payload)
    assert b"abc" not in blob
    assert secret_box.decrypt(blob)["access_token"] == "abc"
    assert timedelta(seconds=0) <= timedelta(days=1)


def test_require_secret_rejects_missing_placeholder_and_short_keys():
    import pytest

    from app.config import Settings

    for bad in ("", "   ", "change-me-to-a-long-random-string", "short-key"):
        with pytest.raises(RuntimeError, match="APP_SECRET"):
            Settings(app_secret=bad).require_secret()
    Settings(app_secret="x" * 32).require_secret()


def test_default_settings_have_no_secret(monkeypatch):
    import pytest

    from app.config import Settings

    monkeypatch.delenv("APP_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        Settings(_env_file=None).require_secret()


def test_old_sha256_records_are_still_readable_and_new_ones_are_not_legacy():
    import json
    import os
    from hashlib import sha256

    import pytest
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from app.config import settings

    legacy = AESGCM(sha256(settings.app_secret.encode("utf-8")).digest())
    nonce = os.urandom(12)
    old_blob = nonce + legacy.encrypt(nonce, json.dumps({"access_token": "old"}).encode("utf-8"), None)
    assert secret_box.decrypt(old_blob) == {"access_token": "old"}

    new_blob = secret_box.encrypt({"access_token": "new"})
    assert secret_box.decrypt(new_blob) == {"access_token": "new"}
    with pytest.raises(InvalidTag):
        legacy.decrypt(new_blob[:12], new_blob[12:], None)


def test_wrong_key_is_rejected(monkeypatch):
    import pytest
    from cryptography.exceptions import InvalidTag

    from app.config import settings

    blob = secret_box.encrypt({"a": 1})
    monkeypatch.setattr(settings, "app_secret", "another-secret-0123456789abcdef0123456789")
    with pytest.raises(InvalidTag):
        secret_box.decrypt(blob)
