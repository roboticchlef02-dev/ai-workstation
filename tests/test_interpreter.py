"""Strategy interpreter (D-027). Model code is never run here: a fake verifier reads a
`# passes ...` comment instead of executing anything. Sandboxed runs are in test_runner.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiws.arms import Solver
from aiws.benchmark import Case, Task
from aiws.budget import BudgetCaps, Ledger
from aiws.interpreter import StrategyRunError, parse_generated_tests, run_strategy
from aiws.metered import CallContext, MeteredClient
from aiws.prices import PriceTable
from aiws.providers.mock import MockProvider
from aiws.strategy import load_library
from aiws.telemetry import Telemetry

ROOT = Path(__file__).resolve().parents[1]
LIB = load_library(ROOT / "strategies", max_calls_cap=20)
CTX = CallContext(experiment_id="e", run_id="r", arm="x", task_id="t")
TASK = Task(id="t", category="c", difficulty=1, entry_point="f", signature="def f(x):",
            statement="Return the thing.",
            visible_tests=[Case(args=["v0"], expected=1), Case(args=["v1"], expected=2)])


def code(*passes: str) -> str:
    return f"# passes {' '.join(passes)}\ndef f(x):\n    return 0\n"


def reply(c: str) -> str:
    return f"```python\n{c}```"


def fake_verifier(code_text: str, cases: list[Case]) -> tuple[int, list[str]]:
    first = code_text.splitlines()[0] if code_text else ""
    ok = set(first.removeprefix("# passes ").split()) if first.startswith("# passes") else set()
    fails = [f"f({json.dumps(c.args[0])}) wrong" for c in cases if c.args[0] not in ok]
    return len(cases) - len(fails), fails


@pytest.fixture
def make_solver(tmp_path):
    prices = PriceTable.load(_prices(tmp_path))
    caps = BudgetCaps(global_usd=10, per_experiment_usd=5, per_run_usd=2, per_task_usd=1,
                      per_call_usd=0.5, max_calls_per_task=20, max_output_tokens_per_call=4096)
    ledger = Ledger(tmp_path / "l.sqlite", caps)
    tel = Telemetry(tmp_path / "t.sqlite")

    def make(model_id: str, script) -> tuple[Solver, list[str]]:
        prompts: list[str] = []

        def recorded(req):
            prompts.append(req.messages[-1].content)
            return script(req.messages[-1].content) if callable(script) else script.pop(0)

        client = MeteredClient(MockProvider(model_id=model_id, script=recorded), ledger=ledger,
                               prices=prices, telemetry=tel)
        return Solver(client, model_id, max_output_tokens=512, backoff_s=0), prompts
    return make


def _prices(tmp_path) -> Path:
    p = tmp_path / "prices.yaml"
    entry = ("{provider: mock, periods: [{valid_from: 2026-01-01, input_per_mtok: 0, "
             "output_per_mtok: 0, source: t, verified: true}]}")
    p.write_text(f"version: t\ncurrency: USD\nmodels:\n  mock-1: {entry}\n  mock-2: {entry}\n")
    return p


def run(strategy_id, slots, verifier=fake_verifier):
    return run_strategy(LIB[strategy_id], TASK, slots, verifier, CTX)


def test_single_makes_one_call(make_solver):
    s, _ = make_solver("mock-1", [reply(code("v0"))])
    o = run("single", {"m1": s})
    assert o.model_calls == 1 and not o.visible_pass and o.rounds_used == 0
    assert o.strategy_id == "single"


def test_repair_until_pass(make_solver):
    s, prompts = make_solver("mock-1", [reply(code()), reply(code("v0")), reply(code("v0", "v1"))])
    o = run("repair", {"m1": s})
    assert o.visible_pass and o.model_calls == 3 and o.rounds_used == 2
    assert [t["step"] for t in o.trace] == ["solve", "repair1", "repair2"]
    assert "f(\"v1\") wrong" in prompts[2]  # failures are fed back


def test_repair_keeps_the_best_candidate(make_solver):
    """M1 reviewer #1b: a worse repair never replaces a better candidate."""
    s, _ = make_solver("mock-1", [reply(code("v0")), reply(code()), "no code", reply(code())])
    o = run("repair", {"m1": s})
    assert o.model_calls == 4 and o.code == code("v0") and not o.visible_pass


def test_duo_picks_passing_candidate_without_repair(make_solver):
    a, _ = make_solver("mock-1", [reply(code("v0"))])
    b, _ = make_solver("mock-2", [reply(code("v0", "v1"))])
    o = run("duo", {"m1": a, "m2": b})
    assert o.visible_pass and o.model_calls == 2 and o.winner_model == "mock-2"


def test_duo_other_model_repairs(make_solver):
    a, _ = make_solver("mock-1", [reply(code("v0"))])
    b, b_prompts = make_solver("mock-2", [reply(code()), reply(code("v0", "v1"))])
    o = run("duo", {"m1": a, "m2": b})
    assert o.visible_pass and o.model_calls == 3 and o.winner_model == "mock-2"
    assert o.trace[-1] == {"step": "repair1", "model": "mock-2", "visible": "2/2"}
    assert code("v0") in b_prompts[1]  # m2 repairs m1's better candidate


def test_duo_ties_go_to_the_first_solver(make_solver):
    a, _ = make_solver("mock-1", [reply(code("v0", "v1"))])
    b, _ = make_solver("mock-2", [reply(code("v0", "v1"))])
    assert run("duo", {"m1": a, "m2": b}).winner_model == "mock-1"


def gen_json(*items) -> str:
    return "```json\n" + json.dumps([{"args": [a], "expected": e} for a, e in items]) + "\n```"


def test_selftest_repairs_against_generated_tests(make_solver):
    s, prompts = make_solver("mock-1", [
        reply(code("v0", "v1", "g0")),                 # solve: passes visible, misses g1
        gen_json(("g0", 5), ("g1", 6)),               # generated tests
        reply(code("v0", "v1", "g0", "g1")),            # repair against generated tests
    ])
    o = run("selftest", {"m1": s})
    assert o.visible_pass and o.model_calls == 3 and o.code == code("v0", "v1", "g0", "g1")
    assert o.generated_tests == 2 and o.trace[-1]["generated"] == "2/2"
    assert "```python" not in prompts[1]  # tests are written from the statement, not the code
    assert "may themselves be wrong" in prompts[2] and 'f("g1") wrong' in prompts[2]


def test_selftest_never_trades_a_visible_example_for_generated_tests(make_solver):
    s, _ = make_solver("mock-1", [
        reply(code("v0", "v1")), gen_json(("g0", 5)), reply(code("v0", "g0"))])
    o = run("selftest", {"m1": s})
    assert o.code == code("v0", "v1") and o.visible_pass


def test_selftest_without_usable_tests_finishes(make_solver):
    s, _ = make_solver("mock-1", [reply(code("v0", "v1")), "I can't write tests."])
    o = run("selftest", {"m1": s})
    assert o.visible_pass and o.model_calls == 2 and o.generated_tests == 0


def test_unbound_slot_refused(make_solver):
    a, _ = make_solver("mock-1", [])
    with pytest.raises(StrategyRunError):
        run("duo", {"m1": a})


def test_unvalidated_strategy_over_its_call_budget_refused(make_solver):
    """Defense in depth: the interpreter re-checks worst-case calls against max_calls."""
    s, _ = make_solver("mock-1", [])
    sneaky = LIB["repair"].model_copy(update={"max_calls": 1})
    with pytest.raises(StrategyRunError):
        run_strategy(sneaky, TASK, {"m1": s}, fake_verifier, CTX)


# --- generated tests are untrusted model output ------------------------------------------

def test_parse_generated_tests_filters():
    items = [{"args": ["v0"], "expected": 9},          # same args as a visible example
             {"args": ["a", "b"], "expected": 1},      # wrong arity
             {"args": ["s"], "expected": "str"},       # wrong kind (visible expect numbers)
             {"args": ["n"], "expected": float("nan")},
             {"args": ["x"], "expected": 1, "why": "extra key"},
             {"args": "notalist", "expected": 1},
             {"args": ["ok1"], "expected": 3}, {"args": ["ok1"], "expected": 4},  # dup args
             {"args": ["ok2"], "expected": 4.5}]
    text = "```json\n" + json.dumps(items) + "\n```"
    got = parse_generated_tests(text, TASK)
    assert [(c.args, c.expected) for c in got] == [(["ok1"], 3), (["ok2"], 4.5)]


def test_parse_generated_tests_caps_count_and_survives_garbage():
    many = "```json\n" + json.dumps([{"args": [f"a{i}"], "expected": i} for i in range(50)]) + "```"
    assert len(parse_generated_tests(many, TASK)) == 8
    for junk in ["", "no json", "```json\n{\"args\": 1}\n```", "[" * 100000 + "]" * 100000,
                 "```json\n[1, 2, 3]\n```", '```json\n[{"args": [' + "[" * 5000 + "]" * 5000
                 + '], "expected": 1}]\n```', "x" * 200000]:
        assert parse_generated_tests(junk, TASK) == [] or isinstance(
            parse_generated_tests(junk, TASK), list)
