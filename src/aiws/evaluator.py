"""Evaluator: a separate process that scores submissions on hidden tests (PLAN 6.5, A10).

Protocol: one JSON object per line on stdin {"task_id", "code", "pool"}; one JSON object per
line on stdout. It reads hidden tests from its own benchmark path (never from the request),
refuses to start if the benchmark changed since build, and returns the minimum the pool
allows: HELD_OUT/VALIDATION get pass/fail only; SEED/TRAIN also get pass counts. Hidden
inputs and expected values never appear in a response.

M1 limitation (recorded in D-025): same OS user as the orchestrator; separate identity is M4.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from aiws.benchmark import check, load_hidden_cases, load_tasks, run_cases, verify_manifest
from aiws.executor import SandboxExecutor
from aiws.secretguard import child_env

EVALUATOR_VERSION = "0.1.0"
POOLS = {"SEED", "TRAIN", "VALIDATION", "HELD_OUT"}
_SRC = str(Path(__file__).resolve().parents[1])


class Evaluator:
    def __init__(self, benchmark_root: Path | str, executor: SandboxExecutor | None = None):
        self.root = Path(benchmark_root)
        self.benchmark_sha256 = verify_manifest(self.root)  # raises if tampered
        self.tasks = {t.id: t for t in load_tasks(self.root)}
        self.executor = executor or SandboxExecutor()

    def evaluate(self, task_id: str, code: str, pool: str) -> dict[str, Any]:
        if pool not in POOLS:
            return {"task_id": task_id, "error": f"unknown pool {pool!r}"}
        task = self.tasks.get(task_id)
        if task is None:
            return {"task_id": task_id, "error": "unknown task"}
        cases = load_hidden_cases(self.root, task_id)
        results, err = run_cases(self.executor, task.entry_point, code, [c.args for c in cases])
        verdicts = check(results, cases, task.compare, task.entry_point)
        n_passed = sum(ok for ok, _ in verdicts)
        out: dict[str, Any] = {"task_id": task_id, "passed": n_passed == len(cases),
                               "evaluator_version": EVALUATOR_VERSION,
                               "benchmark_sha256": self.benchmark_sha256}
        if pool in ("SEED", "TRAIN"):
            out.update(n_passed=n_passed, n_total=len(cases),
                       failure="" if results is not None else err[:200])
        return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", required=True)
    args = ap.parse_args()
    ev = Evaluator(args.benchmark)
    for line in sys.stdin:
        try:
            req = json.loads(line)
            resp = ev.evaluate(str(req["task_id"]), str(req["code"]), str(req["pool"]))
        except Exception as e:  # noqa: BLE001  (one bad request must not kill the evaluator)
            resp = {"error": f"{type(e).__name__}"}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


class EvaluatorClient:
    """Starts the evaluator as a child process with a constructed, key-free environment."""

    def __init__(self, benchmark_root: Path | str):
        self.env = {**child_env(), "PYTHONPATH": _SRC}
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "aiws.evaluator", "--benchmark", str(benchmark_root)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=self.env, text=True, bufsize=1)

    def evaluate(self, task_id: str, code: str, pool: str) -> dict[str, Any]:
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(json.dumps({"task_id": task_id, "code": code, "pool": pool}) + "\n")
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
