from datetime import datetime, timedelta, timezone

from app.security import secret_box


def test_secret_roundtrip():
    payload = {"access_token": "abc", "refresh_token": "def", "expires_at": datetime.now(timezone.utc).isoformat()}
    blob = secret_box.encrypt(payload)
    assert b"abc" not in blob
    assert secret_box.decrypt(blob)["access_token"] == "abc"
    assert timedelta(seconds=0) <= timedelta(days=1)
