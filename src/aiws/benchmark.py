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
    (True != 1). In "float" mode numbers match within a small tolerance. Never raises:
    anything odd (huge ints, deep nesting) is simply not equal."""
    try:
        return _compare(got, expected, mode)
    except (OverflowError, RecursionError, TypeError, ValueError):
        return False


def _compare(got: Any, expected: Any, mode: str) -> bool:
    if isinstance(got, bool) or isinstance(expected, bool):
        return type(got) is type(expected) and got == expected
    if isinstance(got, (int, float)) and isinstance(expected, (int, float)):
        if mode == "float":
            return math.isclose(got, expected, rel_tol=1e-6, abs_tol=1e-9)
        return got == expected
    if isinstance(got, list) and isinstance(expected, list):
        return len(got) == len(expected) and all(
            _compare(g, e, mode) for g, e in zip(got, expected))
    if isinstance(got, dict) and isinstance(expected, dict):
        return got.keys() == expected.keys() and all(
            _compare(got[k], expected[k], mode) for k in got)
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
            return None, "timeout"
        tail = r.stderr.strip().splitlines()[-3:]
        return None, f"crash: exit {r.returncode}: " + " | ".join(tail)[-300:]
    try:
        payload = json.loads(lines[-1][len(marker):])
        if isinstance(payload, dict) and set(payload) == {"load_error"}:
            return None, f"load_error: {str(payload['load_error'])[:500]}"
        return _validated(payload, len(inputs)), ""
    except Exception:  # noqa: BLE001  (code under test can print anything: never crash on it)
        return None, "malformed_output"


def _validated(payload: Any, n: int) -> list[dict[str, Any]]:
    """Accept only {"results": [n items of {"ok": true, "value": …} | {"ok": false, "error": str}]}."""
    if not isinstance(payload, dict) or set(payload) != {"results"}:
        raise ValueError("bad payload")
    results = payload["results"]
    if not isinstance(results, list) or len(results) != n:
        raise ValueError("bad results")
    for item in results:
        if not isinstance(item, dict) or not isinstance(item.get("ok"), bool):
            raise ValueError("bad item")
        if item["ok"] and set(item) != {"ok", "value"}:
            raise ValueError("bad ok item")
        if not item["ok"] and (set(item) != {"ok", "error"} or not isinstance(item["error"], str)):
            raise ValueError("bad error item")
    return results


def failure_category(err: str) -> str:
    """Fixed categories only: free text could carry hidden inputs (reviewer #6)."""
    head = err.split(":", 1)[0]
    return head if head in ("timeout", "crash", "load_error", "malformed_output") else "error"


def check(results: list[dict[str, Any]] | None, cases: list[Case], mode: str,
          entry_point: str) -> list[tuple[bool, str]]:
    """Per-case (passed, message). Messages quote args/got/expected: use for visible tests only."""
    out = []
    for i, case in enumerate(cases):
        if results is None:
            out.append((False, ""))
            continue
        res = results[i]
        try:
            args = ", ".join(json.dumps(a) for a in case.args)
        except (TypeError, ValueError, RecursionError):
            args = "…"
        if not res.get("ok"):
            out.append((False, f"{entry_point}({args}) raised {res.get('error')}"[:400]))
        elif compare(res.get("value"), case.expected, mode):
            out.append((True, ""))
        else:
            out.append((False, f"{entry_point}({args}) returned {json.dumps(res.get('value'))}, "
                               f"expected {json.dumps(case.expected)}"[:400]))
    return out


# --- build + manifest ------------------------------------------------------------------

def _finite(v: Any) -> bool:
    if isinstance(v, float):
        return math.isfinite(v)
    if isinstance(v, list):
        return all(_finite(x) for x in v)
    if isinstance(v, dict):
        return all(_finite(x) for x in v.values())
    return True


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
    digest = hashlib.sha256(json.dumps(actual, sort_keys=True).encode()).hexdigest()
    if digest != manifest["sha256"]:
        raise ValueError("benchmark changed since build: manifest digest mismatch")
    return digest


def build(root: Path | str, executor: SandboxExecutor, version: str) -> dict[str, Any]:
    """Compute hidden expected values from each reference; check the visible examples agree."""
    root = Path(root)
    problems: list[str] = []
    for task in load_tasks(root):
        spec = load_hidden_spec(root, task.id)
        if spec.id != task.id:
            problems.append(f"{task.id}: hidden id mismatch")
            continue
        if not spec.hidden_inputs:
            problems.append(f"{task.id}: no hidden inputs (any code would pass)")
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
        if not all(_finite(c["expected"]) for c in cases):
            problems.append(f"{task.id}: non-finite expected value (NaN/inf)")
            continue
        (root / "hidden" / f"{task.id}.expected.json").write_text(
            json.dumps({"id": task.id, "cases": cases}) + "\n")
    if problems:
        raise ValueError("benchmark build failed:\n" + "\n".join(problems))
    return write_manifest(root, version)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Build a benchmark: compute hidden expected values.")
    ap.add_argument("command", choices=["build", "verify"])
    ap.add_argument("root")
    ap.add_argument("--version", default="")
    args = ap.parse_args()
    if args.command == "build":
        m = build(args.root, SandboxExecutor(), version=args.version or "unversioned")
        print(f"built {len(load_tasks(args.root))} tasks, sha256 {m['sha256']}")
    else:
        print(f"ok, sha256 {verify_manifest(args.root)}")


if __name__ == "__main__":
    main()
