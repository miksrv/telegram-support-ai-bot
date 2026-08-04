import pytest
import requests

import core.llm.engine as engine_module
from core.llm.base import LLMQuotaExceededError, is_quota_error
from core.llm.engine import LLMEngine
from core.llm.groq_provider import GroqProvider
from core.llm.openai_provider import OpenAIProvider


class _FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


def _http_error(status_code, body=None):
    return requests.exceptions.HTTPError(response=_FakeResponse(status_code, body))


def test_engine_resolves_openai_provider():
    engine = LLMEngine(engine_name="openai")
    assert isinstance(engine.provider, OpenAIProvider)
    assert engine.provider.name == "openai"


def test_engine_resolves_groq_provider():
    engine = LLMEngine(engine_name="groq")
    assert isinstance(engine.provider, GroqProvider)
    assert engine.provider.name == "groq"


def test_engine_rejects_unknown_provider():
    with pytest.raises(RuntimeError, match="Unknown LLM_ENGINE"):
        LLMEngine(engine_name="does-not-exist")


def test_engine_complete_delegates_to_active_provider(monkeypatch):
    engine = LLMEngine(engine_name="openai")

    captured = {}

    def fake_complete(self, messages, *, temperature, max_tokens, json_mode=True):
        captured["messages"] = messages
        captured["json_mode"] = json_mode
        return "ok"

    monkeypatch.setattr(OpenAIProvider, "complete", fake_complete)

    result = engine.complete([{"role": "user", "content": "hi"}], temperature=0.5, max_tokens=10)

    assert result == "ok"
    assert captured["json_mode"] is True


# --------------------------------------------------
# is_quota_error — distinguishes billing/quota exhaustion from other errors
# --------------------------------------------------


def test_is_quota_error_detects_known_signals():
    assert is_quota_error(_FakeResponse(402, {})) is True
    assert is_quota_error(_FakeResponse(429, {"error": {"code": "insufficient_quota"}})) is True
    assert is_quota_error(_FakeResponse(429, {"error": {"type": "billing_hard_limit_reached"}})) is True


def test_is_quota_error_ignores_plain_rate_limit_and_other_errors():
    assert is_quota_error(_FakeResponse(429, {"error": {"code": "rate_limit_exceeded"}})) is False
    assert is_quota_error(_FakeResponse(401, {"error": {"code": "invalid_api_key"}})) is False
    assert is_quota_error(_FakeResponse(500, {})) is False
    assert is_quota_error(None) is False


# --------------------------------------------------
# Provider-level conversion of quota HTTP errors
# --------------------------------------------------


def test_openai_provider_converts_quota_http_error(monkeypatch):
    provider = OpenAIProvider()
    monkeypatch.setattr(
        "core.llm.openai_provider.post_with_retry",
        lambda *a, **k: (_ for _ in ()).throw(_http_error(402, {})),
    )

    with pytest.raises(LLMQuotaExceededError):
        provider.complete([{"role": "user", "content": "hi"}], temperature=0.5, max_tokens=10)


def test_openai_provider_passes_through_non_quota_http_error(monkeypatch):
    provider = OpenAIProvider()
    monkeypatch.setattr(
        "core.llm.openai_provider.post_with_retry",
        lambda *a, **k: (_ for _ in ()).throw(_http_error(500, {})),
    )

    with pytest.raises(requests.exceptions.HTTPError):
        provider.complete([{"role": "user", "content": "hi"}], temperature=0.5, max_tokens=10)


def test_groq_provider_converts_quota_http_error(monkeypatch):
    provider = GroqProvider()
    monkeypatch.setattr(
        "core.llm.groq_provider.post_with_retry",
        lambda *a, **k: (_ for _ in ()).throw(_http_error(429, {"error": {"code": "insufficient_quota"}})),
    )

    with pytest.raises(LLMQuotaExceededError):
        provider.complete([{"role": "user", "content": "hi"}], temperature=0.5, max_tokens=10)


def test_groq_provider_passes_through_non_quota_http_error(monkeypatch):
    provider = GroqProvider()
    monkeypatch.setattr(
        "core.llm.groq_provider.post_with_retry",
        lambda *a, **k: (_ for _ in ()).throw(_http_error(401, {"error": {"code": "invalid_api_key"}})),
    )

    with pytest.raises(requests.exceptions.HTTPError):
        provider.complete([{"role": "user", "content": "hi"}], temperature=0.5, max_tokens=10)


def test_provider_sends_the_configured_model(monkeypatch):
    from config.settings import OPENAI_MODEL

    provider = OpenAIProvider()
    captured = {}

    class _FakeResponseWithChoices:
        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(session, url, headers, payload):
        captured["model"] = payload["model"]
        return _FakeResponseWithChoices()

    monkeypatch.setattr("core.llm.openai_provider.post_with_retry", fake_post)

    provider.complete([{"role": "user", "content": "hi"}], temperature=0.5, max_tokens=10)
    assert captured["model"] == OPENAI_MODEL


# --------------------------------------------------
# Engine-level automatic fallback on quota exhaustion — OpenAI is primary,
# Groq is the standby fallback per this bot's spec.
# --------------------------------------------------


def test_engine_builds_fallback_when_other_key_present():
    # conftest sets both OPENAI_API_KEY and GROQ_API_KEY, so the default
    # "openai" primary engine should pick up "groq" as an automatic fallback.
    engine = LLMEngine(engine_name="openai")
    assert isinstance(engine.fallback_provider, GroqProvider)


def test_engine_no_fallback_when_other_key_absent(monkeypatch):
    monkeypatch.setitem(engine_module._PROVIDER_API_KEYS, "groq", "")
    engine = LLMEngine(engine_name="openai")
    assert engine.fallback_provider is None


def test_engine_switches_to_fallback_on_quota_error(monkeypatch):
    engine = LLMEngine(engine_name="openai")
    assert isinstance(engine.fallback_provider, GroqProvider)

    def fake_openai_complete(self, messages, **kw):
        raise LLMQuotaExceededError("openai: out of balance")

    def fake_groq_complete(self, messages, **kw):
        return "from groq"

    monkeypatch.setattr(OpenAIProvider, "complete", fake_openai_complete)
    monkeypatch.setattr(GroqProvider, "complete", fake_groq_complete)

    result = engine.complete([{"role": "user", "content": "hi"}], temperature=0.5, max_tokens=10)

    assert result == "from groq"
    assert engine.provider.name == "groq"
    assert engine.fallback_provider is None  # consumed — no bouncing back


def test_engine_quota_error_without_fallback_propagates(monkeypatch):
    monkeypatch.setitem(engine_module._PROVIDER_API_KEYS, "openai", "")
    engine = LLMEngine(engine_name="groq")
    assert engine.fallback_provider is None

    def fake_complete(self, messages, **kw):
        raise LLMQuotaExceededError("groq: out of balance")

    monkeypatch.setattr(GroqProvider, "complete", fake_complete)

    with pytest.raises(LLMQuotaExceededError):
        engine.complete([{"role": "user", "content": "hi"}], temperature=0.5, max_tokens=10)
