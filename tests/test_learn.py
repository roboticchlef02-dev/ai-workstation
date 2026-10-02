"""M2 learning run end to end with scripted mock models (D-027). The e2e test needs L3."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from aiws import benchmark
from aiws.executor import SandboxExecutor
from aiws.experience import ExperienceLog
from aiws.learn import make_options, mcnemar_p, refuse_protected, run_learning
from aiws.providers.mock import MockProvider
from aiws.strategy import load_library

ROOT = Path(__file__).resolve().parents[1]

TASKS = {
    # id: (category, entry, signature, statement, visible, hidden inputs, reference)
    "t-add": ("numerical", "add", "def add(a, b):", "Return a + b.", [[[1, 2], 3]],
              [[5, 7], [1000, 1]], "def add(a, b):\n    return a + b\n"),
    "t-add2": ("numerical", "add", "def add(a, b):", "Return the sum a + b.", [[[2, 2], 4]],
               [[3, 4], [500, 600]], "def add(a, b):\n    return a + b\n"),
    "t-rev": ("strings", "rev", "def rev(s):", "Reverse s.", [[["ab"], "ba"]],
              [["xyz"], ["hello"]], "def rev(s):\n    return s[::-1]\n"),
    "t-rev2": ("strings", "rev", "def rev(s):", "Return s reversed.", [[["no"], "on"]],
               [["abc"], ["racecar!"]], "def rev(s):\n    return s[::-1]\n"),
}
# Plausible but wrong: passes the one visible example, fails larger hidden inputs.
PARTIAL = {"add": "def add(a, b):\n    return a + b if a < 100 else 0\n",
           "rev": "def rev(s):\n    return s[::-1] if len(s) < 3 else s\n"}
RIGHT = {"add": "def add(a, b):\n    return a + b\n", "rev": "def rev(s):\n    return s[::-1]\n"}
EDGE = {"add": [{"args": [100, 1], "expected": 101}],
        "rev": [{"args": ["abc"], "expected": "cba"}]}


def make_bench(root: Path) -> Path:
    (root / "tasks").mkdir(parents=True)
    (root / "hidden").mkdir()
    for tid, (cat, entry, sig, stmt, vis, hid, ref) in TASKS.items():
        (root / "tasks" / f"{tid}.yaml").write_text(yaml.safe_dump({
            "id": tid, "category": cat, "difficulty": 1, "entry_point": entry,
            "signature": sig, "statement": stmt,
            "visible_tests": [{"args": a, "expected": e} for a, e in vis]}))
        (root / "hidden" / f"{tid}.yaml").write_text(yaml.safe_dump({
            "id": tid, "hidden_inputs": hid, "reference_solution": ref}))
    return root


def scripted(req) -> str:
    p = req.messages[-1].content
    name = "add" if "def add" in p else "rev"
    if "Write extra test cases" in p:
        return "```json\n" + json.dumps(EDGE[name]) + "\n```"
    if "may themselves be wrong" in p:
        return f"```python\n{RIGHT[name]}```"
    return f"```python\n{PARTIAL[name]}```"  # solve and plain repair: the plausible bug


@pytest.mark.needs_l3
def test_learning_run_end_to_end(tmp_path):
    ex = SandboxExecutor()
    if ex.isolation_level() != "L3":
        pytest.skip(ex.why_not_l3())
    bench = make_bench(tmp_path / "bench")
    benchmark.build(bench, ex, version="t")
    providers = [(MockProvider(model_id="mock-1", script=scripted), "mock-1")]
    r = run_learning(models=[], strategies=["repair", "selftest"], benchmark=bench,
                     split_seed=1, seed=1, per_task=2, confirm_spend=False, pool="SEED",
                     max_out=512, out_dir=tmp_path / "out", state_dir=tmp_path / "state",
                     interval=0.0, providers=providers, log=lambda *_: None)
    train_ids = set(r["config"]["train_tasks"])
    eval_ids = set(r["config"]["eval_tasks"])
    assert len(train_ids) == 2 and len(eval_ids) == 2 and not train_ids & eval_ids

    # TRAIN: both options tried on each task; selftest catches the bug, repair can't see it.
    assert {(x["task_id"], x["option"]) for x in r["train_rows"]} == {
        (t, o) for t in train_ids for o in ("repair@1", "selftest@1")}
    assert all(x["passed"] == (x["option"] == "selftest@1") for x in r["train_rows"])
    assert r["picks"] == {"numerical": "selftest@1", "strings": "selftest@1"}

    # The experience log holds TRAIN rows only: EVAL outcomes never reach learning.
    logged = ExperienceLog(tmp_path / "state" / "experience.sqlite").rows()
    assert {x.task_id for x in logged} == train_ids and len(logged) == 4
    assert all(x.pool == "TRAIN" for x in logged)

    # EVAL: every option on every task; warm (selftest) beats cold (repair).
    assert {(x["task_id"], x["option"]) for x in r["eval_rows"]} == {
        (t, o) for t in eval_ids for o in ("repair@1", "selftest@1")}
    report = r["report_path"].read_text()
    assert "| **warm** (frozen selector) | 2/2 |" in report
    assert "| **cold** (repair@1) | 0/2 |" in report
    assert "only warm solved: 2, only cold solved: 0" in report
    out = r["report_path"].parent
    assert {p.name for p in out.iterdir()} >= {"config.json", "train.jsonl", "eval.jsonl",
                                              "selector.json", "report.md"}


def test_refuses_protected_benchmark_paths():
    for p in (ROOT / "benchmarks" / "held_out", ROOT / "benchmarks" / "held_out" / "x",
              ROOT / "secrets", Path("/tmp/elsewhere/held_out/tasks")):
        with pytest.raises(SystemExit):
            refuse_protected(p)
    refuse_protected(ROOT / "benchmarks" / "seed")  # allowed


def test_options_bind_slots_to_models():
    lib = load_library(ROOT / "strategies", max_calls_cap=20)
    keys2 = [o.key for o in make_options(lib, 2)]
    assert set(keys2) == {"single@1", "single@2", "repair@1", "repair@2", "selftest@1",
                          "selftest@2", "duo@1+2"}
    assert "duo@1+1" in [o.key for o in make_options(lib, 1)]


def test_mcnemar_exact():
    assert mcnemar_p(0, 0) == 1.0
    assert mcnemar_p(5, 0) == pytest.approx(0.0625)
    assert mcnemar_p(3, 3) == 1.0
