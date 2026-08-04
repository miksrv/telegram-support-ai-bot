import requests

from core.llm import base as llm_base
from core.llm.base import post_with_retry


class _FakeHTTPResponse:
    def __init__(self, status_code, body=None, headers=None):
        self.status_code = status_code
        self._body = body or {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)

    def json(self):
        return self._body


class _FakeSession:
    """Stands in for requests.Session — returns queued responses in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def post(self, url, headers=None, json=None, timeout=None):  # noqa: A002
        self.calls += 1
        return self._responses.pop(0)


def test_post_with_retry_retries_plain_rate_limit(monkeypatch):
    monkeypatch.setattr(llm_base.time, "sleep", lambda s: None)
    session = _FakeSession(
        [
            _FakeHTTPResponse(429, {"error": {"code": "rate_limit_exceeded"}}),
            _FakeHTTPResponse(200, {"ok": True}),
        ]
    )

    response = post_with_retry(session, "http://example/api", {}, {})

    assert response.status_code == 200
    assert session.calls == 2


def test_post_with_retry_does_not_retry_quota_429(monkeypatch):
    monkeypatch.setattr(llm_base.time, "sleep", lambda s: None)
    session = _FakeSession(
        [
            _FakeHTTPResponse(429, {"error": {"code": "insufficient_quota"}}),
            _FakeHTTPResponse(200, {"ok": True}),
        ]
    )

    try:
        post_with_retry(session, "http://example/api", {}, {})
        assert False, "expected HTTPError to propagate"
    except requests.exceptions.HTTPError:
        pass

    assert session.calls == 1  # no retry wasted on a quota error


def test_post_with_retry_does_not_retry_other_http_errors(monkeypatch):
    monkeypatch.setattr(llm_base.time, "sleep", lambda s: None)
    session = _FakeSession([_FakeHTTPResponse(401, {"error": {"code": "invalid_api_key"}})])

    try:
        post_with_retry(session, "http://example/api", {}, {})
        assert False, "expected HTTPError to propagate"
    except requests.exceptions.HTTPError:
        pass

    assert session.calls == 1


def test_post_with_retry_honors_retry_after_header(monkeypatch):
    slept = []
    monkeypatch.setattr(llm_base.time, "sleep", slept.append)
    session = _FakeSession(
        [
            _FakeHTTPResponse(429, {"error": {}}, headers={"Retry-After": "5"}),
            _FakeHTTPResponse(200, {"ok": True}),
        ]
    )

    post_with_retry(session, "http://example/api", {}, {})

    assert slept == [5.0]


def test_post_with_retry_gives_up_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(llm_base.time, "sleep", lambda s: None)
    session = _FakeSession([_FakeHTTPResponse(429, {"error": {}}) for _ in range(3)])

    try:
        post_with_retry(session, "http://example/api", {}, {}, retries=3)
        assert False, "expected HTTPError to propagate"
    except requests.exceptions.HTTPError:
        pass

    assert session.calls == 3


def test_post_with_retry_retries_connection_error_then_succeeds(monkeypatch):
    monkeypatch.setattr(llm_base.time, "sleep", lambda s: None)

    calls = {"n": 0}

    class _FlakySession:
        def post(self, url, headers=None, json=None, timeout=None):  # noqa: A002
            calls["n"] += 1
            if calls["n"] == 1:
                raise requests.exceptions.ConnectionError("boom")
            return _FakeHTTPResponse(200, {"ok": True})

    response = post_with_retry(_FlakySession(), "http://example/api", {}, {})
    assert response.status_code == 200
    assert calls["n"] == 2


def test_is_quota_error_variants():
    from core.llm.base import is_quota_error

    assert is_quota_error(None) is False
    assert is_quota_error(_FakeHTTPResponse(402, {})) is True
    assert is_quota_error(_FakeHTTPResponse(429, {"error": {"code": "insufficient_quota"}})) is True
    assert is_quota_error(_FakeHTTPResponse(429, {"error": {"code": "rate_limit_exceeded"}})) is False
    assert is_quota_error(_FakeHTTPResponse(500, {})) is False


def test_is_quota_error_handles_non_json_body():
    class _BadJsonResponse:
        status_code = 429

        def json(self):
            raise ValueError("not json")

    from core.llm.base import is_quota_error

    assert is_quota_error(_BadJsonResponse()) is False


def test_post_with_retry_falls_back_to_backoff_on_garbage_retry_after(monkeypatch):
    slept = []
    monkeypatch.setattr(llm_base.time, "sleep", slept.append)
    session = _FakeSession(
        [
            _FakeHTTPResponse(429, {"error": {}}, headers={"Retry-After": "not-a-number"}),
            _FakeHTTPResponse(200, {"ok": True}),
        ]
    )

    post_with_retry(session, "http://example/api", {}, {})

    assert slept == [1]  # 2**0 exponential backoff, not the garbage header value
