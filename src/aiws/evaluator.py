"""Evaluator: a separate process that scores submissions on hidden tests (PLAN 6.5, A10).

Protocol: one JSON object per line on stdin {"task_id", "code", "pool"}; one JSON object per
line on stdout. It reads hidden tests from its own benchmark path (never from the request),
refuses to start if the benchmark changed since build, and returns the minimum the pool
allows: HELD_OUT/VALIDATION get pass/fail only; SEED/TRAIN also get pass counts. Hidden
inputs and expected values never appear in a response.

The pool is set at startup (--pool), not per request. Failures are reported as fixed
categories (timeout, crash, load_error, malformed_output), never as free text.
M1 limitation (recorded in D-025): same OS user as the orchestrator; separate identity is M4.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from aiws.benchmark import (
    check,
    failure_category,
    load_hidden_cases,
    load_tasks,
    run_cases,
    verify_manifest,
)
from aiws.executor import SandboxExecutor
from aiws.secretguard import child_env

EVALUATOR_VERSION = "0.2.0"
POOLS = {"SEED", "TRAIN", "VALIDATION", "HELD_OUT"}
_SRC = str(Path(__file__).resolve().parents[1])
_HERE = Path(__file__).resolve().parent


def code_sha256() -> str:
    """Hash of the code that decides verdicts. A change means a new evaluator version
    (PLAN 6.5: never compare scores across evaluator versions)."""
    h = hashlib.sha256()
    for name in ("evaluator.py", "benchmark.py", "harness.py", "executor.py"):
        h.update((_HERE / name).read_bytes())
    return h.hexdigest()


class Evaluator:
    """The pool is fixed when the evaluator starts, from its own config, never per request
    (reviewer #6). Hidden cases are loaded and hash-checked once, at startup."""

    def __init__(self, benchmark_root: Path | str, pool: str = "SEED",
                 executor: SandboxExecutor | None = None):
        if pool not in POOLS:
            raise ValueError(f"unknown pool {pool!r}")
        self.root = Path(benchmark_root)
        self.pool = pool
        self.benchmark_sha256 = verify_manifest(self.root)  # raises if tampered
        self.tasks = {t.id: t for t in load_tasks(self.root)}
        self.cases = {tid: load_hidden_cases(self.root, tid) for tid in self.tasks}
        if verify_manifest(self.root) != self.benchmark_sha256:  # nothing changed while loading
            raise ValueError("benchmark changed while loading")
        self.code_sha256 = code_sha256()
        self.executor = executor or SandboxExecutor()

    def info(self) -> dict[str, Any]:
        return {"evaluator_version": EVALUATOR_VERSION, "evaluator_code_sha256": self.code_sha256,
                "benchmark_sha256": self.benchmark_sha256, "pool": self.pool,
                "n_tasks": len(self.tasks)}

    def evaluate(self, task_id: str, code: str, pool: str) -> dict[str, Any]:
        if pool != self.pool:
            return {"task_id": task_id, "error": f"this evaluator serves pool {self.pool}"}
        task = self.tasks.get(task_id)
        if task is None:
            return {"task_id": task_id, "error": "unknown task"}
        cases = self.cases[task_id]
        results, err = run_cases(self.executor, task.entry_point, code, [c.args for c in cases])
        verdicts = check(results, cases, task.compare, task.entry_point)
        n_passed = sum(ok for ok, _ in verdicts)
        out: dict[str, Any] = {"task_id": task_id, "passed": n_passed == len(cases),
                               "evaluator_version": EVALUATOR_VERSION,
                               "benchmark_sha256": self.benchmark_sha256}
        if self.pool in ("SEED", "TRAIN"):
            # Counts and a fixed failure category only: never messages, inputs or values.
            out.update(n_passed=n_passed, n_total=len(cases),
                       failure="" if results is not None else failure_category(err))
        return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", required=True)
    ap.add_argument("--pool", required=True, choices=sorted(POOLS))
    args = ap.parse_args()
    ev = Evaluator(args.benchmark, pool=args.pool)
    for line in sys.stdin:
        try:
            req = json.loads(line)
            if req.get("op") == "info":
                resp = ev.info()
            else:
                resp = ev.evaluate(str(req["task_id"]), str(req["code"]), str(req["pool"]))
        except Exception as e:  # noqa: BLE001  (one bad request must not kill the evaluator)
            resp = {"error": f"{type(e).__name__}"}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


class EvaluatorClient:
    """Starts the evaluator as a child process with a constructed, key-free environment."""

    def __init__(self, benchmark_root: Path | str, pool: str = "SEED"):
        self.env = {**child_env(), "PYTHONPATH": _SRC}
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "aiws.evaluator", "--benchmark", str(benchmark_root),
             "--pool", pool],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=self.env, text=True, bufsize=1)

    def info(self) -> dict[str, Any]:
        return self._ask({"op": "info"})

    def evaluate(self, task_id: str, code: str, pool: str) -> dict[str, Any]:
        return self._ask({"task_id": task_id, "code": code, "pool": pool})

    def _ask(self, req: dict[str, Any]) -> dict[str, Any]:
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError(f"evaluator exited (code {self.proc.poll()})")
        return json.loads(line)

    def close(self) -> None:
        if self.proc.poll() is None:
            assert self.proc.stdin is not None
            self.proc.stdin.close()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def __enter__(self) -> EvaluatorClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


if __name__ == "__main__":
    main()
