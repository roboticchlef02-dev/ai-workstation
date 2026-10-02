"""Google Gemini provider (REST `generateContent`, API key from GEMINI_API_KEY).

The key is read at call time, sent only in the `x-goog-api-key` header (never in the URL),
and never stored on the object, logged or put into an error message.
"""

from __future__ import annotations

import os
import time
from typing import Any, Literal

import httpx

from aiws.providers.base import (
    Capabilities,
    GenerateRequest,
    GenerateResponse,
    ModelProvider,
    ProviderError,
    Usage,
)
from aiws.secretguard import redact

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_SAMPLING_FIELDS = {"temperature": "temperature", "top_p": "topP", "top_k": "topK",
                    "seed": "seed"}


class GeminiProvider(ModelProvider):
    name = "gemini"

    def __init__(self, *, model_id: str, billing_tier: Literal["free", "paid"],
                 key_env: str = "GEMINI_API_KEY", client: httpx.Client | None = None,
                 timeout_s: float = 180.0):
        if billing_tier not in ("free", "paid"):
            raise ValueError("billing_tier must be 'free' or 'paid' (recorded on every call)")
        self.model_id, self.billing_tier, self._key_env = model_id, billing_tier, key_env
        self._client = client or httpx.Client()
        self._timeout = timeout_s

    def get_model_id(self) -> str:
        return self.model_id

    def get_capabilities(self, model_id: str | None = None) -> Capabilities:
        return Capabilities(sampling_params=frozenset(_SAMPLING_FIELDS), max_output_tokens=65536)

    @staticmethod
    def _body(req: GenerateRequest, sampling: dict[str, Any]) -> dict[str, Any]:
        config: dict[str, Any] = {"maxOutputTokens": req.max_output_tokens}
        config.update({_SAMPLING_FIELDS[k]: v for k, v in sampling.items()})
        body: dict[str, Any] = {
            "contents": [{"role": "model" if m.role == "assistant" else "user",
                          "parts": [{"text": m.content}]} for m in req.messages],
            "generationConfig": config,
        }
        if req.system:
            body["systemInstruction"] = {"parts": [{"text": req.system}]}
        return body

    def _generate(self, req: GenerateRequest, sampling: dict[str, Any]) -> GenerateResponse:
        if req.model_id != self.model_id:
            raise ProviderError(f"provider serves {self.model_id}, not {req.model_id}",
                                billable=False)
        key = os.environ.get(self._key_env, "")
        if not key:
            raise ProviderError(f"{self._key_env} is not set", billable=False)
        url = f"{BASE_URL}/models/{self.model_id}:generateContent"
        t0 = time.monotonic()
        try:
            r = self._client.post(url, json=self._body(req, sampling), timeout=self._timeout,
                                  headers={"x-goog-api-key": key})
        except httpx.ConnectError as e:
            raise ProviderError(redact(f"connect error: {e}"), billable=False,
                                retryable=True) from None
        except httpx.TimeoutException as e:
            raise ProviderError(redact(f"timeout: {e}"), billable=None, retryable=True) from None
        except httpx.HTTPError as e:
            raise ProviderError(redact(f"transport error: {e}"), billable=None) from None
        finally:
            del key
        latency = time.monotonic() - t0
        if r.status_code != 200:
            raise self._http_error(r)
        data = r.json()
        return self._parse(req, data, latency)

    @staticmethod
    def _http_error(r: httpx.Response) -> ProviderError:
        try:
            message = str(r.json().get("error", {}).get("message", ""))[:300]
        except ValueError:
            message = r.text[:300]
        text = redact(f"gemini HTTP {r.status_code}: {message}")
        if r.status_code == 429:
            return ProviderError(text, billable=False, retryable=True)
        if r.status_code >= 500:
            return ProviderError(text, billable=None, retryable=True)
        return ProviderError(text, billable=False)  # 4xx: rejected before generation

    def _parse(self, req: GenerateRequest, data: dict[str, Any],
               latency: float) -> GenerateResponse:
        usage = data.get("usageMetadata") or {}
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise ProviderError(f"gemini returned no answer: {reason}", billable=None)
        cand = candidates[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        thoughts = int(usage.get("thoughtsTokenCount", 0))
        return GenerateResponse(
            provider=self.name, model_id=req.model_id,
            model_version=str(data.get("modelVersion", "unknown")),
            request_id=str(data.get("responseId", "")),
            text=text,
            usage=Usage(input_tokens=int(usage.get("promptTokenCount", 0)),
                        output_tokens=int(usage.get("candidatesTokenCount", 0)) + thoughts,
                        thinking_tokens=thoughts),
            latency_s=latency, finish_reason=str(cand.get("finishReason", "UNKNOWN")),
            requested_sampling={}, effective_sampling={}, billing_tier=self.billing_tier,
            metadata={"total_token_count": usage.get("totalTokenCount")},
        )
