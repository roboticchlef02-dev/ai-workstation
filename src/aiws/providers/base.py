"""Provider-neutral request/response types and the `ModelProvider` interface (PLAN 6.1, A12)."""

from __future__ import annotations

import hashlib
import json
import math
from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aiws.prices import PriceTable


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    role: Literal["user", "assistant"]
    content: str


class Sampling(BaseModel):
    """Requested sampling. A provider drops what its model doesn't support (A12)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    seed: int | None = None

    def requested(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model_id: str
    system: str = ""
    messages: tuple[Message, ...]
    max_output_tokens: int = Field(gt=0)  # includes thinking tokens
    sampling: Sampling = Sampling()

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


class Usage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)    # includes thinking tokens (billed as output)
    thinking_tokens: int = Field(default=0, ge=0)


class GenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    model_id: str                 # the ID that was requested (price-table key)
    model_version: str            # what the provider says actually served the call
    request_id: str
    text: str
    usage: Usage
    latency_s: float
    finish_reason: str
    requested_sampling: dict[str, Any]
    effective_sampling: dict[str, Any]
    metadata: dict[str, Any] = {}
    billing_tier: Literal["paid", "free", "none"]
    replayed: bool = False


class Capabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sampling_params: frozenset[str]
    max_output_tokens: int


class ProviderError(Exception):
    """A call failed. `sent` says whether the request may have reached (and been billed by)
    the provider: False = certainly not sent, True = sent, None = unknown."""

    def __init__(self, message: str, *, sent: bool | None):
        super().__init__(message)
        self.sent = sent


# Conservative input-token estimate for reservations: ~3 characters per token + overhead.
_CHARS_PER_TOKEN = 3
_TOKENS_PER_MESSAGE = 8


def estimate_input_tokens(req: GenerateRequest) -> int:
    chars = len(req.system) + sum(len(m.content) for m in req.messages)
    return math.ceil(chars / _CHARS_PER_TOKEN) + _TOKENS_PER_MESSAGE * (len(req.messages) + 1)


class ModelProvider(ABC):
    name: str
    billing_tier: Literal["paid", "free", "none"]

    @abstractmethod
    def get_model_id(self) -> str: ...

    @abstractmethod
    def get_capabilities(self, model_id: str | None = None) -> Capabilities: ...

    @abstractmethod
    def _generate(self, req: GenerateRequest, sampling: dict[str, Any]) -> GenerateResponse:
        """Send the request with the effective sampling params. Raise ProviderError on failure."""

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        requested = req.sampling.requested()
        supported = self.get_capabilities(req.model_id).sampling_params
        effective = {k: v for k, v in requested.items() if k in supported}
        resp = self._generate(req, effective)
        return resp.model_copy(update={"requested_sampling": requested,
                                       "effective_sampling": effective})

    def estimate_cost_usd(self, req: GenerateRequest, prices: PriceTable, *, on: date) -> float:
        """Worst case: estimated input + the full output allowance. Raises if unpriced."""
        micro = prices.cost_microusd(req.model_id, estimate_input_tokens(req),
                                     req.max_output_tokens, on=on)
        return micro / 1_000_000
