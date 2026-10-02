"""End-to-end M1 loop with scripted mock models on a synthetic benchmark (needs L3)."""

from __future__ import annotations

import json

import pytest

from aiws import benchmark
from aiws.arms import extract_code
from aiws.executor import SandboxExecutor
from aiws.providers.mock import MockProvider
from aiws.run import run_experiment
from test_evaluator import make_bench

WRONG = {"add": "def add(a, b):\n    return a - b\n", "rev": "def rev(s):\n    return s\n"}
RIGHT = {"add": "def add(a, b):\n    return a + b\n", "rev": "def rev(s):\n    return s[::-1]\n"}


def scripted(req):
    prompt = req.messages[-1].content
    name = "add" if "def add" in prompt else "rev"
    code = RIGHT[name] if "Current code:" in prompt else WRONG[name]  # fixes only when repairing
    return f"Here you go:\n```python\n{code}```\n"


def test_extract_code_variants():
    assert extract_code("```python\ndef f():\n    return 1\n```") == "def f():\n    return 1\n"
    two = "```python\ndef f(): return 1\n```\ntext\n```py\ndef f(): return 2\n```"
    assert "return 2" in extract_code(two)
    assert extract_code("def f(): return 3") == "def f(): return 3\n"
    assert extract_code("I cannot help with that.") == ""


@pytest.mark.needs_l3
def test_full_loop_with_mock_models(tmp_path):
    ex = SandboxExecutor()
    if ex.isolation_level() != "L3":
        pytest.skip(ex.why_not_l3())
    bench = make_bench(tmp_path / "bench")
    benchmark.build(bench, ex, version="t")
    providers = [(MockProvider(model_id="mock-1", script=scripted), "mock-1"),
                 (MockProvider(model_id="mock-1", script=scripted), "mock-1")]
    r = run_experiment(models=[], arm_list=None, benchmark=bench, limit=None,
                       task_ids=None, seed=3, confirm_spend=False, pool="SEED",
                       rounds={"A": 0, "C": 3, "D": 2}, max_out=512, out_dir=tmp_path / "out",
                       state_dir=tmp_path / "state", interval=0.0, providers=providers,
                       log=lambda *_: None)
    got = {(row["task_id"], row["arm"]): row for row in r["rows"]}
    assert r["config"]["arms"] == ["A1", "C1", "A2", "C2", "D"]  # every arm for 2 models
    assert len(got) == 10
    for tid in ("t-add", "t-rev"):
        for a in ("A1", "A2"):
            assert got[(tid, a)]["passed"] is False and got[(tid, a)]["model_calls"] == 1
        for c in ("C1", "C2"):
            assert got[(tid, c)]["passed"] is True and got[(tid, c)]["model_calls"] == 2
        assert got[(tid, "D")]["passed"] is True and got[(tid, "D")]["model_calls"] == 3
    report = r["report_path"].read_text()
    assert "| A1 single shot (mock-1) | 0/2 |" in report
    assert "| C1 execute + repair (mock-1) | 2/2 |" in report
    assert "D vs the best single-model arm" in report
    assert r["config"]["fingerprint"]["sha256"] and r["config"]["evaluator_code_sha256"]
    lines = (r["report_path"].parent / "results.jsonl").read_text().splitlines()
    assert len(lines) == 10 and all(json.loads(x)["run_id"] == r["run_id"] for x in lines)


def test_arm_spec_parsing_and_models():
    from aiws.run import arm_models, arm_parts, default_arms
    assert arm_parts("A1") == ("A", 0) and arm_parts("C2") == ("C", 1) and arm_parts("C") == ("C", 0)
    assert arm_models("D", 2) == [0, 1] and arm_models("D", 1) == [0]
    assert default_arms(1) == ["A1", "C1", "D"]
    for bad in ("B1", "D2", "Ax"):
        with pytest.raises(ValueError):
            arm_parts(bad)
    with pytest.raises(ValueError):
        arm_models("A2", 1)


def test_estimate_prices_d_at_the_dearer_model():
    """Reviewer #5: a free second model must not hide a paid first model."""
    from aiws.prices import PriceTable
    from aiws.run import estimate_usd, make_provider
    from aiws.benchmark import Task
    t = Task(id="x", category="c", difficulty=1, entry_point="f", signature="def f():",
             statement="s", visible_tests=[])
    paid, free = make_provider("gemini:gemini-3.8-flash"), make_provider("gemini:gemma-4-31b-it")
    est = estimate_usd([t], ["D"], [paid, free], PriceTable.load(), {"A": 0, "C": 3, "D": 2}, 1000)
    assert est > 0
