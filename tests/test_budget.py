"""M1 security tests: budget caps, shadow cost, reserve-then-settle ledger, spend preflight.

Written before src/aiws/{prices,budget}.py (CLAUDE.md: security tests first).
Covers PLAN 5.3/8 (budget enforcement), R7 (hierarchy, env only lowers, atomic ledger,
reserve-then-settle) and D-016 (list-price shadow cost, even for free-tier calls).
"""

from __future__ import annotations

import math
import multiprocessing as mp
from datetime import date
from pathlib import Path

import pytest
import yaml

from aiws import budget
from aiws.budget import BudgetCaps, BudgetExceeded, Ledger, SpendNotConfirmed
from aiws.prices import PriceTable, UnknownModel

ROOT = Path(__file__).resolve().parents[1]

CAPS = dict(global_usd=10.0, per_experiment_usd=5.0, per_run_usd=2.0, per_task_usd=0.5,
            per_call_usd=0.2, max_calls_per_task=4, max_output_tokens_per_call=4096)


def caps(**over) -> BudgetCaps:
    return BudgetCaps(**{**CAPS, **over})


def ids(**over):
    return {**dict(experiment_id="e1", run_id="r1", arm="A", task_id="t1", model_id="m"), **over}


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "ledger.sqlite", caps())


# --- price table / shadow cost ---------------------------------------------------------

PRICES = {
    "version": "test",
    "currency": "USD",
    "models": {
        "cheap-1": {"provider": "p", "periods": [
            {"valid_from": "2026-01-01", "valid_until": "2026-12-31", "input_per_mtok": 0.75,
             "output_per_mtok": 3.75, "source": "test", "verified": False},
            {"valid_from": "2027-01-01", "input_per_mtok": 1.5, "output_per_mtok": 7.5,
             "source": "test", "verified": False},
        ]},
    },
}


def write_prices(tmp_path, data=PRICES) -> Path:
    p = tmp_path / "prices.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


def test_cost_is_integer_microusd_rounded_up(tmp_path):
    t = PriceTable.load(write_prices(tmp_path))
    # 1 token at $0.75/Mtok = 0.75 micro-USD -> rounded up to 1.
    assert t.cost_microusd("cheap-1", 1, 0, on=date(2026, 10, 2)) == 1
    assert t.cost_microusd("cheap-1", 2000, 1000, on=date(2026, 10, 2)) == 1500 + 3750


def test_price_period_switches_by_date(tmp_path):
    t = PriceTable.load(write_prices(tmp_path))
    assert t.cost_microusd("cheap-1", 0, 1000, on=date(2026, 12, 31)) == 3750
    assert t.cost_microusd("cheap-1", 0, 1000, on=date(2027, 1, 1)) == 7500


def test_unknown_model_or_date_fails_closed(tmp_path):
    t = PriceTable.load(write_prices(tmp_path))
    with pytest.raises(UnknownModel):
        t.cost_microusd("nope", 1, 1, on=date(2026, 10, 2))
    with pytest.raises(UnknownModel):
        t.cost_microusd("cheap-1", 1, 1, on=date(2025, 6, 1))


def test_price_table_rejects_overlaps_and_negatives(tmp_path):
    bad = yaml.safe_load(yaml.safe_dump(PRICES))
    bad["models"]["cheap-1"]["periods"][1]["valid_from"] = "2026-06-01"
    with pytest.raises(ValueError):
        PriceTable.load(write_prices(tmp_path, bad))
    bad = yaml.safe_load(yaml.safe_dump(PRICES))
    bad["models"]["cheap-1"]["periods"][0]["input_per_mtok"] = -1
    with pytest.raises(ValueError):
        PriceTable.load(write_prices(tmp_path, bad))


def test_negative_token_counts_rejected(tmp_path):
    t = PriceTable.load(write_prices(tmp_path))
    with pytest.raises(ValueError):
        t.cost_microusd("cheap-1", -1, 0, on=date(2026, 10, 2))


def test_shipped_price_table_loads_and_is_dated():
    t = PriceTable.load()
    assert t.version
    assert "claude-haiku-4-5-20251001" in t.models


# --- caps: file + env (env may only lower) ---------------------------------------------

def test_shipped_budget_config_loads():
    c = budget.load_caps(env={})
    assert c.per_run_usd == 5.0  # MAX_RUN_COST_USD default (CLAUDE.md)


def write_caps(tmp_path, **over) -> Path:
    p = tmp_path / "budget.yaml"
    p.write_text(yaml.safe_dump({"version": 1, **CAPS, **over}))
    return p


def test_env_can_lower_caps(tmp_path):
    c = budget.load_caps(write_caps(tmp_path),
                         env={"MAX_RUN_COST_USD": "1", "TOTAL_EXPERIMENT_BUDGET_USD": "3"})
    assert c.per_run_usd == 1.0 and c.global_usd == 3.0


def test_env_cannot_raise_caps(tmp_path):
    c = budget.load_caps(write_caps(tmp_path),
                         env={"MAX_RUN_COST_USD": "999", "TOTAL_EXPERIMENT_BUDGET_USD": "1e9"})
    assert c.per_run_usd == CAPS["per_run_usd"] and c.global_usd == CAPS["global_usd"]


def test_empty_env_value_means_unset(tmp_path):
    c = budget.load_caps(write_caps(tmp_path), env={"TOTAL_EXPERIMENT_BUDGET_USD": ""})
    assert c.global_usd == CAPS["global_usd"]


@pytest.mark.parametrize("value", ["abc", "-1", "0", "nan", "inf", "-inf"])
def test_invalid_env_value_fails_closed(tmp_path, value):
    with pytest.raises(ValueError):
        budget.load_caps(write_caps(tmp_path), env={"MAX_RUN_COST_USD": value})


@pytest.mark.parametrize("field,value", [("per_run_usd", -1), ("global_usd", math.inf),
                                         ("per_task_usd", math.nan), ("max_calls_per_task", 0)])
def test_invalid_file_caps_rejected(tmp_path, field, value):
    with pytest.raises(ValueError):
        budget.load_caps(write_caps(tmp_path, **{field: value}), env={})


def test_unknown_field_in_caps_file_rejected(tmp_path):
    with pytest.raises(ValueError):
        budget.load_caps(write_caps(tmp_path, per_task_usdd=1.0), env={})


# --- ledger: reserve / settle / release ------------------------------------------------

def test_reserve_within_caps(ledger):
    rid = ledger.reserve(0.1, **ids())
    assert ledger.committed_usd() == pytest.approx(0.1)
    ledger.settle(rid, shadow_usd=0.03)
    assert ledger.committed_usd() == pytest.approx(0.03)


@pytest.mark.parametrize("level,setup", [
    ("call", lambda l: l.reserve(0.25, **ids())),
    ("task", lambda l: [l.reserve(0.2, **ids()) for _ in range(3)]),
    ("run", lambda l: [l.reserve(0.2, **ids(task_id=f"t{i}")) for i in range(11)]),
    ("experiment", lambda l: [l.reserve(0.2, **ids(run_id=f"r{i // 9}", task_id=f"t{i}"))
                              for i in range(26)]),
    ("global", lambda l: [l.reserve(0.2, **ids(experiment_id=f"e{i // 24}",
                                                run_id=f"r{i // 9}", task_id=f"t{i}"))
                          for i in range(51)]),
])
def test_each_cap_level_is_enforced(ledger, level, setup):
    with pytest.raises(BudgetExceeded) as exc:
        setup(ledger)
    assert exc.value.level == level
    assert ledger.committed_usd() <= CAPS["global_usd"] + 1e-9


def test_open_reservations_count_against_caps(ledger):
    ledger.reserve(0.2, **ids())
    ledger.reserve(0.2, **ids())
    with pytest.raises(BudgetExceeded):
        ledger.reserve(0.2, **ids())  # 0.6 > per_task 0.5, though nothing is settled yet


def test_settling_below_reservation_frees_room(ledger):
    a = ledger.reserve(0.2, **ids())
    b = ledger.reserve(0.2, **ids())
    ledger.settle(a, shadow_usd=0.01)
    ledger.settle(b, shadow_usd=0.01)
    ledger.reserve(0.2, **ids())  # 0.22 <= 0.5


def test_release_frees_room_and_does_not_count_as_call(ledger):
    for _ in range(10):
        ledger.release(ledger.reserve(0.2, **ids()))
    assert ledger.committed_usd() == 0
    ledger.reserve(0.2, **ids())


def test_call_count_cap_per_task(ledger):
    for _ in range(4):
        ledger.settle(ledger.reserve(0.0, **ids()), shadow_usd=0.0)
    with pytest.raises(BudgetExceeded) as exc:
        ledger.reserve(0.0, **ids())
    assert exc.value.level == "task_calls"
    ledger.reserve(0.0, **ids(arm="B"))  # another arm has its own per-task budget


def test_settle_rules(ledger):
    rid = ledger.reserve(0.1, **ids())
    ledger.settle(rid, shadow_usd=0.05)
    with pytest.raises(ValueError):
        ledger.settle(rid, shadow_usd=0.05)  # twice
    with pytest.raises(ValueError):
        ledger.release(rid)  # already settled
    with pytest.raises(KeyError):
        ledger.settle(99999, shadow_usd=0.0)


@pytest.mark.parametrize("amount", [-0.01, math.nan, math.inf])
def test_bad_amounts_rejected(ledger, amount):
    with pytest.raises(ValueError):
        ledger.reserve(amount, **ids())
    rid = ledger.reserve(0.1, **ids())
    with pytest.raises(ValueError):
        ledger.settle(rid, shadow_usd=amount)


def test_overrun_is_recorded_not_hidden(ledger):
    rid = ledger.reserve(0.1, **ids())
    ledger.settle(rid, shadow_usd=0.15)
    assert ledger.committed_usd() == pytest.approx(0.15)
    assert ledger.overruns() == [rid]


def test_free_tier_calls_still_count_at_list_price(ledger):
    """D-016: caps use list-price shadow cost; the billed amount is reported separately."""
    rid = ledger.reserve(0.1, **ids())
    ledger.settle(rid, shadow_usd=0.08, billed_usd=0.0)
    assert ledger.committed_usd() == pytest.approx(0.08)
    assert ledger.billed_usd() == 0.0


def test_running_total_survives_restart(tmp_path):
    path = tmp_path / "ledger.sqlite"
    first = Ledger(path, caps())
    first.settle(first.reserve(0.2, **ids()), shadow_usd=0.2)
    second = Ledger(path, caps())
    assert second.committed_usd() == pytest.approx(0.2)
    assert second.committed_usd(task=("e1", "A", "t1")) == pytest.approx(0.2)


def _race_worker(path: str, n: int, out) -> None:
    led = Ledger(path, caps(global_usd=1.0, per_experiment_usd=1.0, per_run_usd=1.0,
                            per_task_usd=1.0, max_calls_per_task=10_000))
    ok = 0
    for _ in range(n):
        try:
            led.reserve(0.01, **ids())
            ok += 1
        except BudgetExceeded:
            pass
    out.put(ok)


def test_concurrent_reservations_never_exceed_cap(tmp_path):
    """R7: reserve-then-settle under real process concurrency."""
    path = str(tmp_path / "ledger.sqlite")
    Ledger(path, caps())  # create schema
    ctx = mp.get_context("spawn")
    out = ctx.Queue()
    procs = [ctx.Process(target=_race_worker, args=(path, 40, out)) for _ in range(6)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
    granted = sum(out.get(timeout=5) for _ in procs)
    assert granted == 100  # exactly $1.00 / $0.01; 240 attempts
    led = Ledger(path, caps(global_usd=1.0))
    assert led.committed_usd() == pytest.approx(1.0)


# --- spend preflight (CLAUDE.md: --confirm-spend, printed estimate, under the run cap) --

def test_preflight_requires_confirmation_for_any_nonzero_estimate():
    with pytest.raises(SpendNotConfirmed) as exc:
        budget.spend_preflight(0.01, confirm_spend=False, caps=caps())
    assert "0.01" in str(exc.value)  # the refusal still shows the estimate


def test_preflight_zero_cost_needs_no_confirmation():
    budget.spend_preflight(0.0, confirm_spend=False, caps=caps())


def test_preflight_refuses_estimate_over_run_cap():
    with pytest.raises(BudgetExceeded) as exc:
        budget.spend_preflight(2.5, confirm_spend=True, caps=caps())
    assert exc.value.level == "run"


def test_preflight_refuses_estimate_over_global_remaining(ledger):
    ledger.settle(ledger.reserve(0.2, **ids()), shadow_usd=0.2)
    tight = caps(global_usd=1.0, per_run_usd=1.0)
    with pytest.raises(BudgetExceeded) as exc:
        budget.spend_preflight(0.9, confirm_spend=True, caps=tight, ledger=ledger)
    assert exc.value.level == "global"


def test_preflight_ok_returns_printable_estimate(ledger):
    msg = budget.spend_preflight(0.42, confirm_spend=True, caps=caps(), ledger=ledger)
    assert "$0.42" in msg and "$2.00" in msg
