"""The only path from orchestrator code to a model: secret check, budget reservation,
dispatch, settlement, telemetry. Contains no provider-specific logic (PLAN 6.1).

Order matters. Everything that can refuse a call (secret in the prompt, output allowance over
the cap, unpriced model, budget) runs before the request is dispatched.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Any

from aiws.budget import BudgetExceeded, Ledger
from aiws.prices import PriceTable
from aiws.providers.base import GenerateRequest, GenerateResponse, ModelProvider
from aiws.secretguard import assert_no_secret, redact
from aiws.telemetry import Telemetry


@dataclass(frozen=True)
class CallContext:
    experiment_id: str
    run_id: str
    arm: str
    task_id: str


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


class MeteredClient:
    def __init__(self, provider: ModelProvider, *, ledger: Ledger, prices: PriceTable,
                 telemetry: Telemetry, today: Callable[[], date] = _utc_today):
        self.provider, self.ledger, self.prices = provider, ledger, prices
        self.telemetry, self._today = telemetry, today

    def generate(self, req: GenerateRequest, ctx: CallContext) -> GenerateResponse:
        assert_no_secret(req)  # never send a secret to a model
        cap = self.ledger.caps.max_output_tokens_per_call
        if req.max_output_tokens > cap:
            raise BudgetExceeded("call_tokens", cap, 0, req.max_output_tokens)
        on = self._today()
        reserved = self.provider.estimate_cost_usd(req, self.prices, on=on)  # unpriced -> raises
        rid = self.ledger.reserve(reserved, model_id=req.model_id, **asdict(ctx))
        paid = self.provider.billing_tier == "paid"
        t0 = time.monotonic()
        try:
            resp = self.provider.generate(req)
        except BaseException as e:
            if getattr(e, "billable", None) is False:
                self.ledger.release(rid)
                shadow = billed = 0.0
            else:  # billed or unknown: charge the worst case
                shadow, billed = reserved, (reserved if paid else 0.0)
                self.ledger.settle(rid, shadow_usd=shadow, billed_usd=billed)
            self._record(req, ctx, None, time.monotonic() - t0, reserved, shadow, billed, e)
            raise
        latency = time.monotonic() - t0
        if resp.replayed:
            shadow = 0.0
        else:
            shadow = self.prices.cost_microusd(req.model_id, resp.usage.input_tokens,
                                               resp.usage.output_tokens, on=on) / 1_000_000
        billed = shadow if paid and not resp.replayed else 0.0
        self.ledger.settle(rid, shadow_usd=shadow, billed_usd=billed)
        self._record(req, ctx, resp, latency, reserved, shadow, billed, None)
        return resp

    def _record(self, req: GenerateRequest, ctx: CallContext, resp: GenerateResponse | None,
                latency: float, reserved: float, shadow: float, billed: float,
                error: BaseException | None) -> None:
        rec: dict[str, Any] = {
            **asdict(ctx),
            "provider": self.provider.name,
            "model_id": req.model_id,
            "model_version": resp.model_version if resp else None,
            "request_id": resp.request_id if resp else None,
            "input_tokens": resp.usage.input_tokens if resp else None,
            "output_tokens": resp.usage.output_tokens if resp else None,
            "thinking_tokens": resp.usage.thinking_tokens if resp else None,
            "reserved_usd": reserved,
            "shadow_usd": shadow,
            "billed_usd": billed,
            "latency_s": round(latency, 6),
            "finish_reason": resp.finish_reason if resp else None,
            "requested_sampling": req.sampling.requested(),
            "effective_sampling": resp.effective_sampling if resp else None,
            "replayed": bool(resp and resp.replayed),
            "billing_tier": self.provider.billing_tier,
            "ok": error is None,
            "error": redact(f"{type(error).__name__}: {error}") if error else None,
            "prompt_sha256": req.sha256(),
            "response_sha256": hashlib.sha256(resp.text.encode()).hexdigest() if resp else None,
        }
        self.telemetry.write_call(rec)
