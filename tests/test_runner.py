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
    r = run_experiment(models=[], arm_list=["A", "C", "D"], benchmark=bench, limit=None,
                       task_ids=None, seed=3, confirm_spend=False, pool="SEED",
                       rounds={"A": 0, "C": 3, "D": 2}, max_out=512, out_dir=tmp_path / "out",
                       state_dir=tmp_path / "state", interval=0.0, providers=providers,
                       log=lambda *_: None)
    got = {(row["task_id"], row["arm"]): row for row in r["rows"]}
    assert len(got) == 6
    for tid in ("t-add", "t-rev"):
        assert got[(tid, "A")]["passed"] is False and got[(tid, "A")]["model_calls"] == 1
        assert got[(tid, "C")]["passed"] is True and got[(tid, "C")]["model_calls"] == 2
        assert got[(tid, "D")]["passed"] is True and got[(tid, "D")]["model_calls"] == 3
    report = r["report_path"].read_text()
    assert "| A single shot | 0/2 |" in report and "| C execute + repair | 2/2 |" in report
    lines = (r["report_path"].parent / "results.jsonl").read_text().splitlines()
    assert len(lines) == 6 and all(json.loads(x)["run_id"] == r["run_id"] for x in lines)
