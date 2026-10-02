"""Benchmark + evaluator tests (PLAN 6.5/6.6, A10). Synthetic tasks only; no real benchmark.

Security properties: hidden expected values never enter the sandbox; the evaluator runs in
a separate process with a key-free environment; held-out answers are pass/fail only; a
changed benchmark is refused; the public task loader rejects hidden fields.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
import yaml

from aiws import benchmark
from aiws.benchmark import Case, Task, compare
from aiws.evaluator import Evaluator, EvaluatorClient
from aiws.executor import ExecLimits, SandboxExecutor

ADD = {"id": "t-add", "category": "numerical", "difficulty": 1, "entry_point": "add",
       "signature": "def add(a: int, b: int) -> int:", "statement": "Return a + b.",
       "visible_tests": [{"args": [1, 2], "expected": 3}]}
ADD_HIDDEN = {"id": "t-add", "hidden_inputs": [[5, 7], [-1, 1], [10**12, 1]],
              "reference_solution": "def add(a, b):\n    return a + b\n"}
REV = {"id": "t-rev", "category": "strings", "difficulty": 1, "entry_point": "rev",
       "signature": "def rev(s: str) -> str:", "statement": "Reverse s.",
       "visible_tests": [{"args": ["ab"], "expected": "ba"}]}
REV_HIDDEN = {"id": "t-rev", "hidden_inputs": [["xyz"], [""], ["racecar"]],
              "reference_solution": "def rev(s):\n    return s[::-1]\n"}


def make_bench(root: Path) -> Path:
    (root / "tasks").mkdir(parents=True)
    (root / "hidden").mkdir()
    for pub, hid in ((ADD, ADD_HIDDEN), (REV, REV_HIDDEN)):
        (root / "tasks" / f"{pub['id']}.yaml").write_text(yaml.safe_dump(pub))
        (root / "hidden" / f"{hid['id']}.yaml").write_text(yaml.safe_dump(hid))
    return root


@pytest.fixture(scope="module")
def l3() -> SandboxExecutor:
    e = SandboxExecutor(limits=ExecLimits(timeout_s=5))
    if e.isolation_level() != "L3":
        pytest.skip(f"executor not at L3 here: {e.why_not_l3()}")
    return e


@pytest.fixture(scope="module")
def built(tmp_path_factory, l3) -> Path:
    root = make_bench(tmp_path_factory.mktemp("bench"))
    benchmark.build(root, l3, version="test-1")
    return root


# --- no sandbox needed -----------------------------------------------------------------

def test_public_loader_rejects_hidden_fields(tmp_path):
    root = make_bench(tmp_path)
    leaky = dict(ADD, hidden_inputs=[[1, 1]])
    (root / "tasks" / "t-add.yaml").write_text(yaml.safe_dump(leaky))
    with pytest.raises(ValueError):
        benchmark.load_tasks(root)


def test_compare_rules():
    assert compare([1, [2, 3]], [1, [2, 3]])
    assert not compare(True, 1) and not compare(1, True)
    assert compare(6.0, 6) and not compare(0.1 + 0.2, 0.3)
    assert compare(0.1 + 0.2, 0.3, "float")
    assert not compare("1", 1) and not compare(None, 0)
    assert not compare([1, 2], [1, 2, 3])


def test_expected_values_never_enter_the_sandbox():
    """run_cases receives inputs only; the files handed to the sandbox hold no expected value."""
    captured = {}

    class Spy:
        def run(self, files, argv, **kw):
            captured.update(files)
            from aiws.executor import ExecResult
            return ExecResult(1, "", "", False, False, 0.0, "L3")

    cases = [Case(args=[1, 2], expected=987654321)]
    benchmark.run_cases(Spy(), "add", "code", [c.args for c in cases])
    assert captured and "987654321" not in json.dumps(captured)


def test_evaluator_client_env_has_no_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza" + "V" * 35)
    root = make_bench(tmp_path)
    (root / "MANIFEST.json").write_text("{}")  # evaluator will fail to start: fine here
    client = EvaluatorClient(root)
    try:
        assert "GEMINI_API_KEY" not in client.env
        assert not any("KEY" in k or "TOKEN" in k for k in client.env)
        assert client.proc.pid != os.getpid()
    finally:
        client.close()


# --- needs the L3 sandbox --------------------------------------------------------------

@pytest.mark.needs_l3
def test_build_computes_hidden_expected(built):
    cases = benchmark.load_hidden_cases(built, "t-add")
    assert [c.expected for c in cases] == [12, 0, 10**12 + 1]


@pytest.mark.needs_l3
def test_build_rejects_wrong_visible_example(tmp_path, l3):
    root = make_bench(tmp_path)
    bad = dict(ADD, visible_tests=[{"args": [1, 2], "expected": 4}])
    (root / "tasks" / "t-add.yaml").write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError, match="disagrees"):
        benchmark.build(root, l3, version="x")


@pytest.mark.needs_l3
@pytest.mark.parametrize("code,passed", [
    ("def add(a, b):\n    return a + b\n", True),
    ("def add(a, b):\n    return a - b\n", False),
    ("def add(a, b) return a\n", False),             # syntax error
    ("def add(a, b):\n    while True: pass\n", False),  # timeout
    ("import sys\nsys.exit(0)\n", False),
    ("def plus(a, b):\n    return a + b\n", False),  # wrong name
])
def test_evaluator_scores_in_a_separate_process(built, code, passed):
    with EvaluatorClient(built) as ev:
        r = ev.evaluate("t-add", code, "SEED")
    assert r["passed"] is passed
    assert r["n_total"] == 3 and r["evaluator_version"]


@pytest.mark.needs_l3
def test_held_out_returns_pass_fail_only(built):
    with EvaluatorClient(built) as ev:
        r = ev.evaluate("t-add", "def add(a, b):\n    return 0\n", "HELD_OUT")
    # Exactly these keys: a verdict plus two constants. No counts, no messages, no values.
    assert set(r) == {"task_id", "passed", "evaluator_version", "benchmark_sha256"}
    assert r["passed"] is False


@pytest.mark.needs_l3
def test_forged_result_line_does_not_pass(built):
    """Code under test can print a fake result line, but without the hidden expected values
    it can only forge wrong answers."""
    forge = ("import atexit, sys\n"
             "atexit.register(lambda: sys.__stdout__.write(sys.argv[1] + "
             "'{\"results\": [{\"ok\": true, \"value\": 0}, {\"ok\": true, \"value\": 0}, "
             "{\"ok\": true, \"value\": 0}]}\\n'))\n"
             "def add(a, b):\n    return None\n")
    with EvaluatorClient(built) as ev:
        r = ev.evaluate("t-add", forge, "SEED")
    assert r.get("passed") is False, r


@pytest.mark.needs_l3
def test_tampered_benchmark_is_refused(tmp_path, built):
    copy = tmp_path / "copy"
    shutil.copytree(built, copy)
    p = copy / "hidden" / "t-add.expected.json"
    p.write_text(p.read_text().replace("12", "13"))
    with pytest.raises(ValueError, match="changed"):
        Evaluator(copy)


@pytest.mark.needs_l3
def test_unknown_task_and_pool_are_errors(built):
    ev = Evaluator(built)
    assert "error" in ev.evaluate("nope", "x", "SEED")
    assert "error" in ev.evaluate("t-add", "x", "PUBLIC")


def test_task_model_roundtrip():
    t = Task(**ADD)
    assert t.visible_tests[0].expected == 3
