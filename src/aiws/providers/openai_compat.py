"""Generic OpenAI-compatible chat-completions provider (D-023).

One class covers OpenCode Zen, OpenRouter, Groq and local servers (Ollama, llama.cpp,
LM Studio). Our model IDs are namespaced (`opencode/big-pickle`); `api_model` is the name
the server expects. The key is read at call time and sent only in the Authorization header.
"""

from __future__ import annotations

import os
import time
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from aiws.providers.base import (
    Capabilities,
    GenerateRequest,
    GenerateResponse,
    ModelProvider,
    ProviderError,
    Usage,
    http_error,
)
from aiws.secretguard import redact

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_SAMPLING = frozenset({"temperature", "top_p", "seed"})  # top_k is not in the OpenAI API


class OpenAICompatProvider(ModelProvider):
    def __init__(self, *, name: str, base_url: str, model_id: str,
                 billing_tier: Literal["free", "paid", "none"], key_env: str | None,
                 api_model: str | None = None, client: httpx.Client | None = None,
                 timeout_s: float = 300.0):
        url = urlparse(base_url)
        local = url.hostname in _LOCAL_HOSTS
        if url.scheme != "https" and not local:
            raise ValueError("remote providers must use https (keys are never sent in clear)")
        if key_env is None and not local:
            raise ValueError("a remote provider needs key_env")
        if billing_tier not in ("free", "paid", "none"):
            raise ValueError("billing_tier must be 'free', 'paid' or 'none'")
        self.name, self.base_url = name, base_url.rstrip("/")
        self.model_id, self.api_model = model_id, api_model or model_id
        self.billing_tier, self._key_env = billing_tier, key_env
        self._client = client or httpx.Client()
        self._timeout = timeout_s

    def get_model_id(self) -> str:
        return self.model_id

    def get_capabilities(self, model_id: str | None = None) -> Capabilities:
        return Capabilities(sampling_params=_SAMPLING, max_output_tokens=65536)

    def _body(self, req: GenerateRequest, sampling: dict[str, Any]) -> dict[str, Any]:
        messages = [{"role": "system", "content": req.system}] if req.system else []
        messages += [{"role": m.role, "content": m.content} for m in req.messages]
        return {"model": self.api_model, "messages": messages,
                "max_tokens": req.max_output_tokens, **sampling}

    def _generate(self, req: GenerateRequest, sampling: dict[str, Any]) -> GenerateResponse:
        if req.model_id != self.model_id:
            raise ProviderError(f"provider serves {self.model_id}, not {req.model_id}",
                                billable=False)
        headers = {}
        if self._key_env is not None:
            key = os.environ.get(self._key_env, "")
            if not key:
                raise ProviderError(f"{self._key_env} is not set", billable=False)
            headers["authorization"] = f"Bearer {key}"
            del key
        t0 = time.monotonic()
        try:
            r = self._client.post(f"{self.base_url}/chat/completions", headers=headers,
                                  json=self._body(req, sampling), timeout=self._timeout)
        except httpx.ConnectError as e:
            raise ProviderError(redact(f"connect error: {e}"), billable=False,
                                retryable=True) from None
        except httpx.TimeoutException as e:
            raise ProviderError(redact(f"timeout: {e}"), billable=None, retryable=True) from None
        except httpx.HTTPError as e:
            raise ProviderError(redact(f"transport error: {e}"), billable=None) from None
        finally:
            headers.clear()
        if r.status_code != 200:
            raise http_error(self.name, r)
        return self._parse(req, r.json(), time.monotonic() - t0)

    def _parse(self, req: GenerateRequest, data: dict[str, Any],
               latency: float) -> GenerateResponse:
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(f"{self.name} returned no choices", billable=None)
        choice = choices[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        return GenerateResponse(
            provider=self.name, model_id=req.model_id,
            model_version=str(data.get("model", "unknown")),
            request_id=str(data.get("id", "")),
            text=message.get("content") or "",  # reasoning fields are not part of the answer
            usage=Usage(input_tokens=int(usage.get("prompt_tokens", 0)),
                        output_tokens=int(usage.get("completion_tokens", 0)),
                        thinking_tokens=int(details.get("reasoning_tokens", 0) or 0)),
            latency_s=latency, finish_reason=str(choice.get("finish_reason", "unknown")),
            requested_sampling={}, effective_sampling={}, billing_tier=self.billing_tier,
        )
