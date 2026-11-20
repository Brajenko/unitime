import pytest

from app.adapters import link
from app.models import BusyIntervalRow
from app.security import hash_password, verify_password


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/calendar.ics",
        "http://localhost/calendar.ics",
        "http://10.0.0.5/calendar.ics",
        "http://169.254.169.254/latest/meta-data",
        "ftp://example.com/calendar.ics",
        "file:///etc/passwd",
    ],
)
def test_internal_and_non_http_urls_are_rejected(url):
    with pytest.raises(link.LinkError):
        link.check_url(url)


def test_webcal_scheme_is_normalized():
    assert link.normalize_url(" webcal://example.com/a.ics ") == "https://example.com/a.ics"


def test_busy_rows_have_no_title_columns():
    columns = {column.name for column in BusyIntervalRow.__table__.columns}
    assert not columns & {"summary", "title", "description", "location", "name"}


def test_password_hash_roundtrip():
    stored = hash_password("correct horse battery")
    assert "correct horse" not in stored
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong password!", stored)
    assert not verify_password("anything", None)
    assert hash_password("x" * 8) != hash_password("x" * 8)
