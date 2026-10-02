"""Budget caps and the spend ledger (PLAN 5.3, R7, D-016).

- Caps come from configs/budget.yaml (Control plane). Environment variables may only lower them.
- Every model call reserves its worst-case shadow cost first and settles the actual cost after.
  Open reservations count against every cap, so concurrent callers can't overspend.
- The ledger is a SQLite file; reservations happen inside `BEGIN IMMEDIATE`, which serializes
  writers across threads and processes. The running total survives restarts.
- Amounts are stored as integer micro-USD.
"""

from __future__ import annotations

import math
import os
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

DEFAULT_CAPS_PATH = Path(__file__).resolve().parents[2] / "configs" / "budget.yaml"

# Environment variable -> cap field. An env value can only lower the file's value.
ENV_OVERRIDES = {"MAX_RUN_COST_USD": "per_run_usd", "TOTAL_EXPERIMENT_BUDGET_USD": "global_usd"}


class BudgetCaps(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    global_usd: float = Field(gt=0)
    per_experiment_usd: float = Field(gt=0)
    per_run_usd: float = Field(gt=0)
    per_task_usd: float = Field(gt=0)
    per_call_usd: float = Field(gt=0)
    max_calls_per_task: int = Field(gt=0)
    max_output_tokens_per_call: int = Field(gt=0)

    @field_validator("global_usd", "per_experiment_usd", "per_run_usd", "per_task_usd",
                     "per_call_usd")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("cap must be finite")
        return v


class BudgetExceeded(Exception):
    def __init__(self, level: str, cap_usd: float, committed_usd: float, requested_usd: float):
        self.level, self.cap_usd = level, cap_usd
        self.committed_usd, self.requested_usd = committed_usd, requested_usd
        super().__init__(f"{level} budget exceeded: committed ${committed_usd:.6f} + requested "
                         f"${requested_usd:.6f} > cap ${cap_usd:.6f}")


class SpendNotConfirmed(Exception):
    """A paid (non-zero shadow cost) run was started without --confirm-spend."""


def load_caps(path: Path | str = DEFAULT_CAPS_PATH,
              env: Mapping[str, str] | None = None) -> BudgetCaps:
    env = os.environ if env is None else env
    data = yaml.safe_load(Path(path).read_text()) or {}
    data.pop("version", None)
    try:
        caps = BudgetCaps(**data)
    except ValidationError as e:
        raise ValueError(f"invalid budget config {path}: {e}") from None
    lowered = {}
    for var, field in ENV_OVERRIDES.items():
        raw = env.get(var, "").strip()
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            raise ValueError(f"{var} must be a number") from None
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{var} must be finite and > 0")
        if value < getattr(caps, field):
            lowered[field] = value
    return caps.model_copy(update=lowered) if lowered else caps


def to_microusd(usd: float) -> int:
    if isinstance(usd, bool) or not isinstance(usd, (int, float)):
        raise ValueError("amount must be a number")
    if not math.isfinite(usd) or usd < 0:
        raise ValueError("amount must be finite and >= 0")
    return int((Decimal(str(usd)) * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


def _usd(micro: int) -> float:
    return micro / 1_000_000


_SCHEMA = """
CREATE TABLE IF NOT EXISTS spend (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    arm TEXT NOT NULL,
    task_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RESERVED', 'SETTLED', 'RELEASED')),
    reserved_microusd INTEGER NOT NULL CHECK (reserved_microusd >= 0),
    shadow_microusd INTEGER CHECK (shadow_microusd >= 0),
    billed_microusd INTEGER CHECK (billed_microusd >= 0),
    overrun INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    settled_at TEXT
);
CREATE INDEX IF NOT EXISTS spend_task ON spend (experiment_id, arm, task_id);
CREATE INDEX IF NOT EXISTS spend_run ON spend (run_id);
"""

# What a row counts against the caps: open reservations at their reserved amount,
# settled rows at their actual shadow cost, released rows not at all.
_COMMITTED = ("COALESCE(SUM(CASE status WHEN 'RESERVED' THEN reserved_microusd "
              "WHEN 'SETTLED' THEN shadow_microusd ELSE 0 END), 0)")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Ledger:
    def __init__(self, path: Path | str, caps: BudgetCaps):
        self.path = str(path)
        self.caps = caps
        with self._connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        # One connection per operation: safe across threads; autocommit + explicit transactions.
        return sqlite3.connect(self.path, timeout=30, isolation_level=None)

    def _sum(self, con: sqlite3.Connection, where: str = "1", args: tuple = ()) -> int:
        return con.execute(f"SELECT {_COMMITTED} FROM spend WHERE {where}", args).fetchone()[0]

    def reserve(self, amount_usd: float, *, experiment_id: str, run_id: str, arm: str,
                task_id: str, model_id: str) -> int:
        """Reserve worst-case shadow cost before a call. Raises BudgetExceeded."""
        amount = to_microusd(amount_usd)
        c = self.caps
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            task = ("experiment_id = ? AND arm = ? AND task_id = ?", (experiment_id, arm, task_id))
            checks = [
                ("call", c.per_call_usd, 0),
                ("task", c.per_task_usd, self._sum(con, *task)),
                ("run", c.per_run_usd, self._sum(con, "run_id = ?", (run_id,))),
                ("experiment", c.per_experiment_usd,
                 self._sum(con, "experiment_id = ?", (experiment_id,))),
                ("global", c.global_usd, self._sum(con)),
            ]
            for level, cap_usd, committed in checks:
                if committed + amount > to_microusd(cap_usd):
                    raise BudgetExceeded(level, cap_usd, _usd(committed), _usd(amount))
                if level == "task":
                    calls = con.execute(
                        f"SELECT COUNT(*) FROM spend WHERE {task[0]} AND status != 'RELEASED'",
                        task[1]).fetchone()[0]
                    if calls >= c.max_calls_per_task:
                        raise BudgetExceeded("task_calls", c.max_calls_per_task, calls, 1)
            cur = con.execute(
                "INSERT INTO spend (experiment_id, run_id, arm, task_id, model_id, status, "
                "reserved_microusd, created_at) VALUES (?, ?, ?, ?, ?, 'RESERVED', ?, ?)",
                (experiment_id, run_id, arm, task_id, model_id, amount, _now()))
            con.execute("COMMIT")
            return int(cur.lastrowid)
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def _finish(self, rid: int, status: str, shadow: int | None, billed: int | None) -> None:
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT status, reserved_microusd FROM spend WHERE id = ?",
                              (rid,)).fetchone()
            if row is None:
                raise KeyError(f"no reservation {rid}")
            if row[0] != "RESERVED":
                raise ValueError(f"reservation {rid} is already {row[0]}")
            overrun = int(shadow is not None and shadow > row[1])
            con.execute("UPDATE spend SET status = ?, shadow_microusd = ?, billed_microusd = ?, "
                        "overrun = ?, settled_at = ? WHERE id = ?",
                        (status, shadow, billed, overrun, _now(), rid))
            con.execute("COMMIT")
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def settle(self, rid: int, *, shadow_usd: float, billed_usd: float = 0.0) -> None:
        """Record the actual cost. A cost above the reservation is kept and flagged as overrun."""
        self._finish(rid, "SETTLED", to_microusd(shadow_usd), to_microusd(billed_usd))

    def release(self, rid: int) -> None:
        """The call was never sent (refused before dispatch). Frees the reservation."""
        self._finish(rid, "RELEASED", None, None)

    def committed_usd(self, *, task: tuple[str, str, str] | None = None, run: str | None = None,
                      experiment: str | None = None) -> float:
        with self._connect() as con:
            if task is not None:
                return _usd(self._sum(con, "experiment_id = ? AND arm = ? AND task_id = ?", task))
            if run is not None:
                return _usd(self._sum(con, "run_id = ?", (run,)))
            if experiment is not None:
                return _usd(self._sum(con, "experiment_id = ?", (experiment,)))
            return _usd(self._sum(con))

    def billed_usd(self) -> float:
        with self._connect() as con:
            return _usd(con.execute("SELECT COALESCE(SUM(billed_microusd), 0) FROM spend")
                        .fetchone()[0])

    def overruns(self) -> list[int]:
        with self._connect() as con:
            return [r[0] for r in con.execute("SELECT id FROM spend WHERE overrun = 1 ORDER BY id")]


def spend_preflight(estimate_usd: float, *, confirm_spend: bool, caps: BudgetCaps,
                    ledger: Ledger | None = None) -> str:
    """Gate before any run that may call a paid API (CLAUDE.md spend rule).

    Returns the estimate line the caller must print. Raises SpendNotConfirmed or BudgetExceeded.
    """
    est = to_microusd(estimate_usd)
    spent = 0 if ledger is None else to_microusd(ledger.committed_usd())
    remaining = max(0, to_microusd(caps.global_usd) - spent)
    line = (f"Estimated cost: ${_usd(est):.2f} (list-price shadow cost) · per-run cap "
            f"${caps.per_run_usd:.2f} · global remaining ${_usd(remaining):.2f}")
    if est == 0:
        return line
    if not confirm_spend:
        raise SpendNotConfirmed(f"{line}. Re-run with --confirm-spend to proceed.")
    if est > to_microusd(caps.per_run_usd):
        raise BudgetExceeded("run", caps.per_run_usd, 0.0, _usd(est))
    if est > remaining:
        raise BudgetExceeded("global", caps.global_usd, _usd(spent), _usd(est))
    return line
