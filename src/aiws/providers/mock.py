"""Deterministic provider for tests and dry runs. Never touches the network."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Sequence
from typing import Any

from aiws.providers.base import (
    Capabilities,
    GenerateRequest,
    GenerateResponse,
    ModelProvider,
    ProviderError,
    Usage,
)


class MockProvider(ModelProvider):
    name = "mock"
    billing_tier = "none"

    def __init__(self, *, model_id: str = "mock-1",
                 script: Sequence[str] | Callable[[GenerateRequest], str] | None = None,
                 fail: ProviderError | None = None):
        """`script`: fixed outputs in order, or a function of the request.
        Default: a deterministic string derived from the request hash."""
        self.model_id = model_id
        self._script = script if callable(script) or script is None else list(script)
        self._fail = fail
        self.calls = 0  # requests that reached this provider

    def get_model_id(self) -> str:
        return self.model_id

    def get_capabilities(self, model_id: str | None = None) -> Capabilities:
        return Capabilities(sampling_params=frozenset({"temperature", "seed"}),
                            max_output_tokens=65536)

    def _next_text(self, req: GenerateRequest) -> str:
        if self._script is None:
            return f"mock:{req.sha256()[:16]}"
        if callable(self._script):
            return self._script(req)
        if not self._script:
            raise ProviderError("mock script exhausted", billable=False)
        return self._script.pop(0)

    def _generate(self, req: GenerateRequest, sampling: dict[str, Any]) -> GenerateResponse:
        self.calls += 1
        if self._fail is not None:
            raise self._fail
        text = self._next_text(req)
        prompt_chars = len(req.system) + sum(len(m.content) for m in req.messages)
        out_tokens = min(req.max_output_tokens, math.ceil(len(text) / 4) or 1)
        return GenerateResponse(
            provider=self.name, model_id=req.model_id, model_version=f"{req.model_id}@mock",
            request_id="mock-" + hashlib.sha256(f"{self.calls}:{req.sha256()}".encode())
            .hexdigest()[:12],
            text=text, usage=Usage(input_tokens=math.ceil(prompt_chars / 4) or 1,
                                   output_tokens=out_tokens),
            latency_s=0.0, finish_reason="stop", requested_sampling={},
            effective_sampling=sampling, billing_tier=self.billing_tier,
        )
