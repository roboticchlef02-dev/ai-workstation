"""M1 tests: provider interface, mock provider, record/replay, metered calls, call telemetry.

Written before src/aiws/{providers,metered,telemetry}.py.
Security properties tested here: a call over budget or carrying a secret is refused *before*
dispatch; spend is settled even when a call fails; telemetry never stores a secret;
replayed calls are flagged and cost nothing; requested vs effective sampling is recorded (A12).
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from aiws.budget import BudgetCaps, BudgetExceeded, Ledger
from aiws.metered import CallContext, MeteredClient
from aiws.prices import PriceTable
from aiws.providers.base import GenerateRequest, Message, ProviderError, Sampling
from aiws.providers.mock import MockProvider
from aiws.providers.replay import RecordReplayProvider, ReplayMiss, ReplayStore
from aiws.secretguard import SecretLeak
from aiws.telemetry import Telemetry

FAKE_KEY = "AIza" + "K" * 35
CAPS = BudgetCaps(global_usd=10, per_experiment_usd=5, per_run_usd=2, per_task_usd=0.5,
                  per_call_usd=0.2, max_calls_per_task=5, max_output_tokens_per_call=4096)
CTX = CallContext(experiment_id="e1", run_id="r1", arm="A", task_id="t1")


def req(text="Write add(a, b).", model="mock-1", max_out=256, **sampling) -> GenerateRequest:
    return GenerateRequest(model_id=model, system="You write Python.",
                           messages=(Message(role="user", content=text),),
                           max_output_tokens=max_out, sampling=Sampling(**sampling))


@pytest.fixture
def prices(tmp_path):
    p = tmp_path / "prices.yaml"
    p.write_text(
        "version: t\ncurrency: USD\nmodels:\n"
        "  mock-1: {provider: mock, periods: [{valid_from: 2026-01-01, input_per_mtok: 0,"
        " output_per_mtok: 0, source: t, verified: true}]}\n"
        "  priced-1: {provider: mock, periods: [{valid_from: 2026-01-01, input_per_mtok: 100,"
        " output_per_mtok: 200, source: t, verified: true}]}\n")
    return PriceTable.load(p)


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "ledger.sqlite", CAPS)


@pytest.fixture
def telemetry(tmp_path):
    return Telemetry(tmp_path / "telemetry.sqlite")


def client(provider, ledger, prices, telemetry):
    return MeteredClient(provider, ledger=ledger, prices=prices, telemetry=telemetry)


# --- request / mock provider -----------------------------------------------------------

def test_request_rejects_unknown_fields_and_bad_values():
    with pytest.raises(ValueError):
        GenerateRequest(model_id="m", messages=(), max_output_tokens=10, tools=["shell"])
    with pytest.raises(ValueError):
        GenerateRequest(model_id="m", messages=(Message(role="user", content="x"),),
                        max_output_tokens=0)
    with pytest.raises(ValueError):
        Message(role="system", content="x")  # system prompt has its own field


def test_mock_is_deterministic_and_reports_usage():
    a, b = MockProvider(), MockProvider()
    r1, r2 = a.generate(req()), b.generate(req())
    assert r1.text == r2.text
    assert r1.usage.input_tokens > 0 and r1.usage.output_tokens > 0
    assert r1.provider == "mock" and r1.model_id == "mock-1" and r1.request_id
    assert a.generate(req("other")).text != r1.text


def test_mock_scripted_outputs_in_order():
    m = MockProvider(script=["first", "second"])
    assert [m.generate(req()).text for _ in range(2)] == ["first", "second"]
    with pytest.raises(ProviderError):
        m.generate(req())  # script exhausted: an error, never a made-up answer


def test_requested_vs_effective_sampling_recorded():
    """A12: unsupported sampling params are dropped, and both sets are recorded."""
    r = MockProvider().generate(req(temperature=0.2, top_p=0.9, seed=7))
    assert r.requested_sampling == {"temperature": 0.2, "top_p": 0.9, "seed": 7}
    assert r.effective_sampling == {"temperature": 0.2, "seed": 7}


def test_interface_methods():
    m = MockProvider()
    assert m.get_model_id() == "mock-1"
    assert "temperature" in m.get_capabilities().sampling_params


# --- record / replay -------------------------------------------------------------------

def test_record_then_replay_is_flagged_and_does_not_call_inner(tmp_path):
    store = ReplayStore(tmp_path / "replay.sqlite")
    inner = MockProvider()
    first = RecordReplayProvider(inner, store, mode="record").generate(req())
    assert not first.replayed and inner.calls == 1
    again = RecordReplayProvider(inner, store, mode="replay").generate(req())
    assert again.replayed and again.text == first.text and inner.calls == 1


def test_replay_miss_never_falls_through_to_a_live_call(tmp_path):
    inner = MockProvider()
    p = RecordReplayProvider(inner, ReplayStore(tmp_path / "r.sqlite"), mode="replay")
    with pytest.raises(ReplayMiss):
        p.generate(req())
    assert inner.calls == 0


def test_replay_key_depends_on_every_request_field(tmp_path):
    store = ReplayStore(tmp_path / "r.sqlite")
    RecordReplayProvider(MockProvider(), store, mode="record").generate(req(temperature=0.0))
    replay = RecordReplayProvider(MockProvider(), store, mode="replay")
    for variant in (req(temperature=0.5), req("x", temperature=0.0),
                    req(max_out=128, temperature=0.0), req(model="mock-2", temperature=0.0)):
        with pytest.raises(ReplayMiss):
            replay.generate(variant)


# --- metered client: budget, secrets, settlement ---------------------------------------

def test_metered_call_settles_actual_shadow_cost(ledger, prices, telemetry):
    m = MockProvider(model_id="priced-1")
    resp = client(m, ledger, prices, telemetry).generate(req(model="priced-1"), CTX)
    u = resp.usage
    expected = (u.input_tokens * 100 + u.output_tokens * 200) / 1e6
    assert ledger.committed_usd() == pytest.approx(expected)
    assert ledger.billed_usd() == 0.0  # mock bills nothing; shadow cost still counts (D-016)


def test_over_budget_call_is_refused_before_dispatch(ledger, prices, telemetry):
    m = MockProvider(model_id="priced-1")
    # 4000 output tokens x $200/Mtok = $0.80 worst case > per-call cap $0.20.
    with pytest.raises(BudgetExceeded):
        client(m, ledger, prices, telemetry).generate(req(model="priced-1", max_out=4000), CTX)
    assert m.calls == 0
    assert ledger.committed_usd() == 0


def test_max_output_tokens_over_cap_is_refused(ledger, prices, telemetry):
    m = MockProvider()
    with pytest.raises(BudgetExceeded) as exc:
        client(m, ledger, prices, telemetry).generate(req(max_out=5000), CTX)
    assert exc.value.level == "call_tokens" and m.calls == 0


def test_unpriced_model_is_refused_before_dispatch(ledger, prices, telemetry):
    m = MockProvider(model_id="unpriced")
    with pytest.raises(LookupError):
        client(m, ledger, prices, telemetry).generate(req(model="unpriced"), CTX)
    assert m.calls == 0


def test_secret_in_prompt_is_refused_before_dispatch(ledger, prices, telemetry):
    m = MockProvider()
    with pytest.raises(SecretLeak):
        client(m, ledger, prices, telemetry).generate(req(f"use key {FAKE_KEY}"), CTX)
    assert m.calls == 0


def test_failed_call_not_sent_releases_reservation(ledger, prices, telemetry):
    m = MockProvider(model_id="priced-1", fail=ProviderError("refused locally", billable=False))
    with pytest.raises(ProviderError):
        client(m, ledger, prices, telemetry).generate(req(model="priced-1"), CTX)
    assert ledger.committed_usd() == 0


@pytest.mark.parametrize("billable", [True, None])
def test_failed_call_possibly_billed_is_charged_worst_case(ledger, prices, telemetry, billable):
    m = MockProvider(model_id="priced-1", fail=ProviderError("timeout", billable=billable))
    with pytest.raises(ProviderError):
        client(m, ledger, prices, telemetry).generate(req(model="priced-1"), CTX)
    assert ledger.committed_usd() > 0  # unknown outcome is charged at the reservation


def test_replayed_call_costs_nothing_and_is_flagged(tmp_path, ledger, prices, telemetry):
    store = ReplayStore(tmp_path / "r.sqlite")
    RecordReplayProvider(MockProvider(model_id="priced-1"), store, mode="record").generate(
        req(model="priced-1"))
    p = RecordReplayProvider(MockProvider(model_id="priced-1"), store, mode="replay")
    resp = client(p, ledger, prices, telemetry).generate(req(model="priced-1"), CTX)
    assert resp.replayed and ledger.committed_usd() == 0
    assert telemetry.calls()[0]["replayed"] is True


# --- telemetry -------------------------------------------------------------------------

def test_telemetry_records_required_call_fields(ledger, prices, telemetry):
    client(MockProvider(), ledger, prices, telemetry).generate(req(temperature=0.1), CTX)
    (rec,) = telemetry.calls()
    for field in ("experiment_id", "run_id", "arm", "task_id", "provider", "model_id",
                  "model_version", "request_id", "input_tokens", "output_tokens", "shadow_usd",
                  "billed_usd", "latency_s", "requested_sampling", "effective_sampling",
                  "replayed", "billing_tier", "ok", "prompt_sha256", "response_sha256"):
        assert field in rec, field
    assert rec["ok"] is True and rec["arm"] == "A"


def test_failed_calls_are_recorded_too(ledger, prices, telemetry):
    m = MockProvider(fail=ProviderError("boom", billable=None))
    with pytest.raises(ProviderError):
        client(m, ledger, prices, telemetry).generate(req(), CTX)
    (rec,) = telemetry.calls()
    assert rec["ok"] is False and "boom" in rec["error"]


def test_telemetry_never_stores_secrets(tmp_path, monkeypatch, ledger, prices):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    t = Telemetry(tmp_path / "t.sqlite")
    # A provider error message that echoes the key must be redacted, not stored.
    m = MockProvider(fail=ProviderError(f"401 for key {FAKE_KEY}", billable=True))
    with pytest.raises(ProviderError):
        client(m, ledger, prices, t).generate(req(), CTX)
    raw = sqlite3.connect(tmp_path / "t.sqlite").execute("SELECT * FROM calls").fetchall()
    assert raw and FAKE_KEY not in json.dumps(raw)
    with pytest.raises(SecretLeak):
        t.write_call({"note": FAKE_KEY})


def test_metered_path_has_no_provider_specific_imports():
    """PLAN 6.1: orchestrator-side code depends on the interface only."""
    import ast
    from pathlib import Path

    import aiws.metered

    tree = ast.parse(Path(aiws.metered.__file__).read_text())
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    provider_mods = {m for m in mods if m.startswith("aiws.providers")}
    assert provider_mods == {"aiws.providers.base"}
