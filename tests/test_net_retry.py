import email.message
import io
import os
import urllib.error

import pytest

import net_retry


def http_error(code, retry_after=None):
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("https://example.test", code, "err", headers, io.BytesIO(b""))


def flaky(errors, result="ok"):
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if errors:
            raise errors.pop(0)
        return result
    return fn, calls


def test_retries_transient_errors_then_succeeds(no_sleep):
    fn, calls = flaky([urllib.error.URLError("reset"), http_error(503)])
    assert net_retry.with_retry(fn, what="test", attempts=3) == "ok"
    assert calls["n"] == 3
    assert no_sleep == [2.0, 4.0]  # backoff exponentiel


def test_does_not_retry_permanent_http_error():
    fn, calls = flaky([http_error(401)])
    with pytest.raises(urllib.error.HTTPError):
        net_retry.with_retry(fn, what="test", attempts=3)
    assert calls["n"] == 1


def test_gives_up_after_max_attempts():
    fn, calls = flaky([TimeoutError()] * 5)
    with pytest.raises(TimeoutError):
        net_retry.with_retry(fn, what="test", attempts=3)
    assert calls["n"] == 3


def test_honours_retry_after_header_capped(no_sleep):
    fn, _ = flaky([http_error(429, retry_after=30), http_error(429, retry_after=500)])
    net_retry.with_retry(fn, what="test", attempts=3, max_delay=60)
    assert no_sleep == [30.0, 60.0]


def test_missing_secret_is_never_retried():
    fn, calls = flaky([net_retry.MissingSecretError("x")])
    with pytest.raises(net_retry.MissingSecretError):
        net_retry.with_retry(fn, what="test", attempts=3)
    assert calls["n"] == 1


@pytest.mark.parametrize("exc,expected", [
    (http_error(429), True),
    (http_error(500), True),
    (http_error(404), False),
    (urllib.error.URLError("dns"), True),
    (ConnectionResetError(), True),
    (ValueError("bad json"), False),
])
def test_is_transient(exc, expected):
    assert net_retry.is_transient(exc) is expected


def test_require_env(monkeypatch):
    monkeypatch.setenv("SOME_KEY", "  abc ")
    assert net_retry.require_env("SOME_KEY", "hint") == "abc"
    monkeypatch.setenv("SOME_KEY", "")
    with pytest.raises(net_retry.MissingSecretError, match="SOME_KEY manquante.*hint"):
        net_retry.require_env("SOME_KEY", "hint")


def test_describe_error_never_leaks_headers():
    assert net_retry.describe_error(http_error(401)) == "HTTP 401 (cle API invalide ou expiree)"
    assert "timeout" in net_retry.describe_error(TimeoutError())


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_download_file_retries_and_writes_atomically(tmp_path, monkeypatch):
    dest = tmp_path / "clip.mp4"
    responses = [urllib.error.URLError("reset"), FakeResponse(b"video-bytes")]

    def fake_urlopen(req, timeout):
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(net_retry.urllib.request, "urlopen", fake_urlopen)
    assert net_retry.download_file("https://x.test/a.mp4", str(dest)) == str(dest)
    assert dest.read_bytes() == b"video-bytes"
    assert not os.path.exists(f"{dest}.part")


def test_download_file_leaves_nothing_on_failure(tmp_path, monkeypatch):
    dest = tmp_path / "clip.mp4"

    def fake_urlopen(req, timeout):
        raise http_error(404)

    monkeypatch.setattr(net_retry.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(urllib.error.HTTPError):
        net_retry.download_file("https://x.test/a.mp4", str(dest))
    assert list(tmp_path.iterdir()) == []
