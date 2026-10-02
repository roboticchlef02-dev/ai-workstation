"""Dated list-price table (configs/prices.yaml) and shadow cost in integer micro-USD (D-016).

Price per 1M tokens in USD equals price per token in micro-USD, so a cost is
tokens x rate, rounded up. Integers keep ledger sums exact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "configs" / "prices.yaml"


class UnknownModel(LookupError):
    """No price for this model on this date. Callers must refuse the call (fail closed)."""


@dataclass(frozen=True)
class PricePeriod:
    valid_from: date
    valid_until: date | None
    input_per_mtok: Decimal
    output_per_mtok: Decimal
    source: str
    verified: bool

    def covers(self, on: date) -> bool:
        return self.valid_from <= on and (self.valid_until is None or on <= self.valid_until)


def _rate(value: object, where: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where}: price must be a number")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{where}: price must be finite and >= 0")
    return Decimal(str(value))


def _date(value: object, where: str) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"{where}: expected a date")


@dataclass(frozen=True)
class PriceTable:
    version: str
    models: dict[str, list[PricePeriod]]

    @classmethod
    def load(cls, path: Path | str = DEFAULT_PATH) -> PriceTable:
        data = yaml.safe_load(Path(path).read_text())
        if data.get("currency") != "USD":
            raise ValueError("price table currency must be USD")
        models: dict[str, list[PricePeriod]] = {}
        for model_id, spec in (data.get("models") or {}).items():
            periods = []
            for i, p in enumerate(spec.get("periods") or []):
                where = f"{model_id}.periods[{i}]"
                until = p.get("valid_until")
                periods.append(PricePeriod(
                    valid_from=_date(p["valid_from"], where),
                    valid_until=_date(until, where) if until is not None else None,
                    input_per_mtok=_rate(p["input_per_mtok"], where),
                    output_per_mtok=_rate(p["output_per_mtok"], where),
                    source=str(p.get("source", "")),
                    verified=bool(p.get("verified", False)),
                ))
            if not periods:
                raise ValueError(f"{model_id}: no price periods")
            periods.sort(key=lambda q: q.valid_from)
            for a, b in zip(periods, periods[1:]):
                if a.valid_until is None or a.valid_until >= b.valid_from:
                    raise ValueError(f"{model_id}: overlapping price periods")
            for q in periods:
                if q.valid_until is not None and q.valid_until < q.valid_from:
                    raise ValueError(f"{model_id}: period ends before it starts")
            models[model_id] = periods
        return cls(version=str(data["version"]), models=models)

    def period(self, model_id: str, on: date) -> PricePeriod:
        for p in self.models.get(model_id, []):
            if p.covers(on):
                return p
        raise UnknownModel(f"no list price for {model_id!r} on {on.isoformat()}")

    def cost_microusd(self, model_id: str, input_tokens: int, output_tokens: int, *,
                      on: date) -> int:
        """Shadow cost. Output tokens include thinking tokens (billed as output)."""
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("token counts must be >= 0")
        p = self.period(model_id, on)
        cost = input_tokens * p.input_per_mtok + output_tokens * p.output_per_mtok
        return int(cost.to_integral_value(rounding=ROUND_CEILING))
