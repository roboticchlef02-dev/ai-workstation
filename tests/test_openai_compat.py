"""OpenAI-compatible provider tests (OpenCode Zen, OpenRouter, Groq, local servers). Offline."""

from __future__ import annotations

import json

import httpx
import pytest

from aiws.providers.base import GenerateRequest, Message, ProviderError, Sampling
from aiws.providers.openai_compat import OpenAICompatProvider

FAKE_KEY = "sk-" + "o" * 40
ZEN = "https://opencode.ai/zen/v1"
MODEL = "opencode/big-pickle"


def req(model=MODEL, **sampling) -> GenerateRequest:
    return GenerateRequest(
        model_id=model, system="You write Python.", max_output_tokens=300,
        messages=(Message(role="user", content="add?"), Message(role="assistant", content="..."),
                  Message(role="user", content="fix")),
        sampling=Sampling(**sampling))


OK_BODY = {
    "id": "chatcmpl-1", "model": "big-pickle-2026-09",
    "choices": [{"index": 0, "finish_reason": "stop", "message": {
        "role": "assistant", "content": "def add(a, b):\n    return a + b\n",
        "reasoning_content": "let me think"}}],
    "usage": {"prompt_tokens": 40, "completion_tokens": 90,
              "completion_tokens_details": {"reasoning_tokens": 60}},
}


def provider(handler, base_url=ZEN, model=MODEL, **kw) -> OpenAICompatProvider:
    kw.setdefault("key_env", "OPENCODE_API_KEY")
    return OpenAICompatProvider(
        name="opencode", base_url=base_url, model_id=model, api_model="big-pickle",
        billing_tier="free", client=httpx.Client(transport=httpx.MockTransport(handler)), **kw)


@pytest.fixture(autouse=True)
def fake_key(monkeypatch):
    monkeypatch.setenv("OPENCODE_API_KEY", FAKE_KEY)


def test_request_shape_and_auth():
    seen = {}

    def handler(request):
        seen["url"], seen["auth"] = str(request.url), request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OK_BODY)

    r = provider(handler).generate(req(temperature=0.3, top_p=0.8, top_k=4, seed=1))
    assert seen["url"] == f"{ZEN}/chat/completions"
    assert FAKE_KEY not in seen["url"] and seen["auth"] == f"Bearer {FAKE_KEY}"
    b = seen["body"]
    assert b["model"] == "big-pickle"  # API name; our namespaced ID stays internal
    assert [m["role"] for m in b["messages"]] == ["system", "user", "assistant", "user"]
    assert b["max_tokens"] == 300
    assert (b["temperature"], b["top_p"], b["seed"]) == (0.3, 0.8, 1) and "top_k" not in b
    assert r.effective_sampling == {"temperature": 0.3, "top_p": 0.8, "seed": 1}


def test_response_parsing_excludes_reasoning_text():
    r = provider(lambda _: httpx.Response(200, json=OK_BODY)).generate(req())
    assert r.text == "def add(a, b):\n    return a + b\n"
    assert (r.usage.input_tokens, r.usage.output_tokens, r.usage.thinking_tokens) == (40, 90, 60)
    assert r.model_id == MODEL and r.model_version == "big-pickle-2026-09"
    assert r.request_id == "chatcmpl-1" and r.provider == "opencode"


def test_null_content_is_an_empty_answer_not_a_crash():
    body = json.loads(json.dumps(OK_BODY))
    body["choices"][0]["message"]["content"] = None
    body["choices"][0]["finish_reason"] = "length"
    r = provider(lambda _: httpx.Response(200, json=body)).generate(req())
    assert r.text == "" and r.finish_reason == "length"


def test_no_choices_is_an_error():
    with pytest.raises(ProviderError) as exc:
        provider(lambda _: httpx.Response(200, json={"id": "x", "choices": []})).generate(req())
    assert exc.value.billable is None


def test_missing_key_fails_before_request(monkeypatch):
    monkeypatch.delenv("OPENCODE_API_KEY")
    calls = []
    with pytest.raises(ProviderError) as exc:
        provider(lambda r: calls.append(r) or httpx.Response(200, json=OK_BODY)).generate(req())
    assert exc.value.billable is False and not calls


@pytest.mark.parametrize("status,billable,retryable", [
    (400, False, False), (401, False, False), (402, False, False), (429, False, True),
    (500, None, True), (502, None, True)])
def test_http_errors_classified_and_redacted(status, billable, retryable):
    body = {"error": {"message": f"bad key {FAKE_KEY}"}}
    with pytest.raises(ProviderError) as exc:
        provider(lambda _: httpx.Response(status, json=body)).generate(req())
    assert (exc.value.billable, exc.value.retryable) == (billable, retryable)
    assert FAKE_KEY not in str(exc.value)


def test_model_mismatch_refused():
    with pytest.raises(ProviderError) as exc:
        provider(lambda _: httpx.Response(200, json=OK_BODY)).generate(req(model="opencode/x"))
    assert exc.value.billable is False


def test_keys_are_never_sent_over_plain_http():
    with pytest.raises(ValueError):
        provider(lambda _: httpx.Response(200, json=OK_BODY), base_url="http://example.com/v1")


def test_local_server_without_key_is_allowed():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=OK_BODY)

    p = provider(handler, base_url="http://127.0.0.1:11434/v1", key_env=None)
    assert p.generate(req()).text
    assert seen["auth"] is None


def test_remote_server_requires_a_key_env():
    with pytest.raises(ValueError):
        provider(lambda _: httpx.Response(200, json=OK_BODY), key_env=None)
