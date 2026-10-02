"""Benchmark tasks: public part (statement + visible examples), hidden part (evaluator only).

Layout of a benchmark directory:
  tasks/<id>.yaml            public: what the workstation and models may see
  hidden/<id>.yaml           hidden inputs + reference solution (evaluator only)
  hidden/<id>.expected.json  hidden expected values, computed by `build` from the reference
  MANIFEST.json              sha256 of every file; the evaluator refuses a changed benchmark

Functions are judged by calling `entry_point(*args)` inside the sandbox (aiws.harness).
Expected values never enter the sandbox; `compare` runs outside it.
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets as _stdlib_secrets
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from aiws.executor import SandboxExecutor

HARNESS_SRC = (Path(__file__).parent / "harness.py").read_text()


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    args: list[Any]
    expected: Any


class Task(BaseModel):
    """Public task. Hidden fields are rejected, so a mixed-up file can't leak them."""
    model_config = ConfigDict(extra="forbid")
    id: str
    category: str
    difficulty: int
    entry_point: str
    signature: str
    statement: str
    visible_tests: list[Case]
    compare: Literal["exact", "float"] = "exact"


class HiddenSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    hidden_inputs: list[list[Any]]
    reference_solution: str


def load_tasks(root: Path | str) -> list[Task]:
    return [Task(**yaml.safe_load(p.read_text()))
            for p in sorted(Path(root, "tasks").glob("*.yaml"))]


def load_hidden_spec(root: Path | str, task_id: str) -> HiddenSpec:
    return HiddenSpec(**yaml.safe_load(Path(root, "hidden", f"{task_id}.yaml").read_text()))


def load_hidden_cases(root: Path | str, task_id: str) -> list[Case]:
    data = json.loads(Path(root, "hidden", f"{task_id}.expected.json").read_text())
    return [Case(**c) for c in data["cases"]]


def compare(got: Any, expected: Any, mode: str = "exact") -> bool:
    """Both sides went through JSON (tuples are lists). Booleans never equal numbers
    (True != 1). In "float" mode numbers match within a small tolerance."""
    if isinstance(got, bool) or isinstance(expected, bool):
        return type(got) is type(expected) and got == expected
    if isinstance(got, (int, float)) and isinstance(expected, (int, float)):
        if mode == "float":
            return math.isclose(got, expected, rel_tol=1e-6, abs_tol=1e-9)
        return got == expected
    if isinstance(got, list) and isinstance(expected, list):
        return len(got) == len(expected) and all(
            compare(g, e, mode) for g, e in zip(got, expected))
    if isinstance(got, dict) and isinstance(expected, dict):
        return got.keys() == expected.keys() and all(
            compare(got[k], expected[k], mode) for k in got)
    return type(got) is type(expected) and got == expected


def run_cases(executor: SandboxExecutor, entry_point: str, code: str,
              inputs: list[list[Any]]) -> tuple[list[dict[str, Any]] | None, str]:
    """Run `entry_point` on each input in the sandbox. Returns (results, error)."""
    marker = "@@AIWS-" + _stdlib_secrets.token_hex(8) + "@@"
    files = {"solution.py": code, "harness.py": HARNESS_SRC, "inputs.json": json.dumps(inputs)}
    r = executor.run(files, ["python3", "harness.py", marker, entry_point])
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith(marker)]
    if not lines:
        if r.timed_out:
            return None, "timed out"
        tail = r.stderr.strip().splitlines()[-3:]
        return None, f"crashed (exit {r.returncode}): " + " | ".join(tail)[-300:]
    try:
        payload = json.loads(lines[-1][len(marker):])
    except ValueError:
        return None, "output too large or malformed"
    if "load_error" in payload:
        return None, f"could not load solution: {payload['load_error']}"
    results = payload.get("results")
    if not isinstance(results, list) or len(results) != len(inputs):
        return None, "harness result mismatch"
    return results, ""


def check(results: list[dict[str, Any]] | None, cases: list[Case], mode: str,
          entry_point: str) -> list[tuple[bool, str]]:
    """Per-case (passed, message). Messages quote args/got/expected: use for visible tests only."""
    out = []
    for i, case in enumerate(cases):
        if results is None:
            out.append((False, ""))
            continue
        res = results[i]
        args = ", ".join(json.dumps(a) for a in case.args)
        if not res.get("ok"):
            out.append((False, f"{entry_point}({args}) raised {res.get('error')}"[:400]))
        elif compare(res.get("value"), case.expected, mode):
            out.append((True, ""))
        else:
            out.append((False, f"{entry_point}({args}) returned {json.dumps(res.get('value'))}, "
                               f"expected {json.dumps(case.expected)}"[:400]))
    return out


# --- build + manifest ------------------------------------------------------------------

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_files(root: Path) -> list[Path]:
    return sorted([*root.glob("tasks/*.yaml"), *root.glob("hidden/*.yaml"),
                   *root.glob("hidden/*.expected.json")])


def write_manifest(root: Path, version: str) -> dict[str, Any]:
    files = {str(p.relative_to(root)): _sha256(p) for p in manifest_files(root)}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    manifest = {"version": version, "files": files, "sha256": digest}
    (root / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest


def verify_manifest(root: Path | str) -> str:
    """Return the benchmark hash if every file matches the manifest; raise otherwise."""
    root = Path(root)
    manifest = json.loads((root / "MANIFEST.json").read_text())
    actual = {str(p.relative_to(root)): _sha256(p) for p in manifest_files(root)}
    if actual != manifest["files"]:
        changed = sorted(set(actual.items()) ^ set(manifest["files"].items()))
        raise ValueError(f"benchmark changed since build: {sorted({c[0] for c in changed})}")
    return manifest["sha256"]


def build(root: Path | str, executor: SandboxExecutor, version: str) -> dict[str, Any]:
    """Compute hidden expected values from each reference; check the visible examples agree."""
    root = Path(root)
    problems: list[str] = []
    for task in load_tasks(root):
        spec = load_hidden_spec(root, task.id)
        if spec.id != task.id:
            problems.append(f"{task.id}: hidden id mismatch")
            continue
        vis_inputs = [c.args for c in task.visible_tests]
        res, err = run_cases(executor, task.entry_point, spec.reference_solution,
                             vis_inputs + spec.hidden_inputs)
        if res is None:
            problems.append(f"{task.id}: reference failed: {err}")
            continue
        for ok, msg in check(res[:len(vis_inputs)], task.visible_tests, task.compare,
                             task.entry_point):
            if not ok:
                problems.append(f"{task.id}: visible example disagrees with reference: {msg}")
        bad = [i for i, r in enumerate(res[len(vis_inputs):]) if not r.get("ok")]
        if bad:
            problems.append(f"{task.id}: reference raised on hidden inputs {bad}")
            continue
        cases = [{"args": a, "expected": r["value"]}
                 for a, r in zip(spec.hidden_inputs, res[len(vis_inputs):])]
        (root / "hidden" / f"{task.id}.expected.json").write_text(
            json.dumps({"id": task.id, "cases": cases}) + "\n")
    if problems:
        raise ValueError("benchmark build failed:\n" + "\n".join(problems))
    return write_manifest(root, version)
