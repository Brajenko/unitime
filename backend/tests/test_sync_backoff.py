import httpx

from app.sync.tasks import Constants, _is_transient, backoff_seconds


def test_backoff_grows_exponentially_and_is_capped():
    assert [backoff_seconds(n) for n in range(5)] == [30, 60, 120, 240, 480]
    assert backoff_seconds(10) == Constants.BACKOFF_MAX_SECONDS


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.com")
    return httpx.HTTPStatusError("x", request=request, response=httpx.Response(code, request=request))


def test_server_errors_are_retried_but_auth_errors_are_not():
    assert _is_transient(_status_error(503))
    assert _is_transient(_status_error(429))
    assert _is_transient(httpx.ConnectTimeout("t"))
    assert not _is_transient(_status_error(401))
    assert not _is_transient(_status_error(403))
