"""Gemini provider tests. Offline: HTTP is served by httpx.MockTransport.

The only network test is marked `live` and is skipped unless --confirm-spend is given.
"""

from __future__ import annotations

import json

import httpx
import pytest

from aiws.providers.base import GenerateRequest, Message, ProviderError, Sampling
from aiws.providers.gemini import GeminiProvider

FAKE_KEY = "AIza" + "G" * 35
MODEL = "gemini-3.8-flash"


def req(**sampling) -> GenerateRequest:
    return GenerateRequest(
        model_id=MODEL, system="You write Python.", max_output_tokens=512,
        messages=(Message(role="user", content="add(a,b)?"),
                  Message(role="assistant", content="def add(a, b): ..."),
                  Message(role="user", content="Fix it.")),
        sampling=Sampling(**sampling))


OK_BODY = {
    "candidates": [{
        "content": {"role": "model", "parts": [
            {"text": "thinking...", "thought": True},
            {"text": "def add(a, b):\n"}, {"text": "    return a + b\n"}]},
        "finishReason": "STOP"}],
    "usageMetadata": {"promptTokenCount": 30, "candidatesTokenCount": 12,
                      "thoughtsTokenCount": 40, "totalTokenCount": 82},
    "modelVersion": "gemini-3.8-flash-001",
    "responseId": "resp-abc",
}


def provider(handler, **kw) -> GeminiProvider:
    return GeminiProvider(model_id=MODEL, billing_tier="free",
                          client=httpx.Client(transport=httpx.MockTransport(handler)), **kw)


@pytest.fixture(autouse=True)
def fake_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)


def test_request_shape_and_auth_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OK_BODY)

    provider(handler).generate(req(temperature=0.2, top_p=0.9, top_k=5, seed=3))
    assert seen["url"].endswith(f"/v1beta/models/{MODEL}:generateContent")
    assert FAKE_KEY not in seen["url"]  # key goes in a header, never the URL
    assert seen["key"] == FAKE_KEY
    body = seen["body"]
    assert body["systemInstruction"] == {"parts": [{"text": "You write Python."}]}
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    assert body["generationConfig"] == {"maxOutputTokens": 512, "temperature": 0.2,
                                        "topP": 0.9, "topK": 5, "seed": 3}


def test_response_parsing_excludes_thoughts_and_counts_them_as_output():
    r = provider(lambda _: httpx.Response(200, json=OK_BODY)).generate(req())
    assert r.text == "def add(a, b):\n    return a + b\n"
    assert r.usage.input_tokens == 30
    assert r.usage.thinking_tokens == 40
    assert r.usage.output_tokens == 52  # candidates + thoughts: both billed as output
    assert r.model_version == "gemini-3.8-flash-001" and r.request_id == "resp-abc"
    assert r.finish_reason == "STOP" and r.billing_tier == "free" and r.provider == "gemini"


def test_missing_key_fails_before_any_request(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    calls = []
    with pytest.raises(ProviderError) as exc:
        provider(lambda r: calls.append(r) or httpx.Response(200, json=OK_BODY)).generate(req())
    assert exc.value.billable is False and not calls


@pytest.mark.parametrize("status,billable,retryable", [
    (400, False, False), (401, False, False), (403, False, False), (404, False, False),
    (429, False, True), (500, None, True), (503, None, True),
])
def test_http_errors_classified(status, billable, retryable):
    body = {"error": {"code": status, "message": f"problem with key {FAKE_KEY}"}}
    with pytest.raises(ProviderError) as exc:
        provider(lambda _: httpx.Response(status, json=body)).generate(req())
    assert exc.value.billable is billable and exc.value.retryable is retryable
    assert str(status) in str(exc.value)
    assert FAKE_KEY not in str(exc.value)  # echoed keys are redacted from the message


def test_timeout_is_unknown_billing():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderError) as exc:
        provider(handler).generate(req())
    assert exc.value.billable is None and exc.value.retryable


def test_connect_error_is_not_billable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderError) as exc:
        provider(handler).generate(req())
    assert exc.value.billable is False and exc.value.retryable


def test_blocked_or_empty_response_is_an_error_not_an_empty_answer():
    body = {"promptFeedback": {"blockReason": "OTHER"},
            "usageMetadata": {"promptTokenCount": 30, "totalTokenCount": 30}}
    with pytest.raises(ProviderError) as exc:
        provider(lambda _: httpx.Response(200, json=body)).generate(req())
    assert exc.value.billable is None


def test_requested_model_must_match_provider_model():
    other = GenerateRequest(model_id="gemini-other", max_output_tokens=8,
                            messages=(Message(role="user", content="x"),))
    with pytest.raises(ProviderError) as exc:
        provider(lambda _: httpx.Response(200, json=OK_BODY)).generate(other)
    assert exc.value.billable is False


def test_billing_tier_must_be_declared():
    with pytest.raises(ValueError):
        GeminiProvider(model_id=MODEL, billing_tier="unknown")


@pytest.mark.live
def test_live_minimal_call(monkeypatch):
    """Spends a few hundred tokens. Runs only with --confirm-spend and a real key."""
    monkeypatch.undo()  # use the real environment's key, not the fake one
    import os
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set")
    p = GeminiProvider(model_id=MODEL, billing_tier="free")
    r = p.generate(GenerateRequest(model_id=MODEL, max_output_tokens=256,
                                   messages=(Message(role="user", content="Reply with OK."),)))
    assert r.text.strip() and r.usage.input_tokens > 0
