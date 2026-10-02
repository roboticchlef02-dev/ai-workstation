"""Strategy DSL v0: strategies are declarative data, never code (law 3, PLAN 6.7, D-027).

A strategy is a linear list of steps over a fixed operator set:
  CALL_MODEL {model: m1|m2, template}       one call; a "code" template adds a candidate,
                                            a "tests" template adds generated test cases
  PARALLEL   {calls: [CALL_MODEL, ...]}     1-3 independent calls
  VERIFY     {tests: visible|visible+generated}
                                            run every candidate in the sandbox; pick the best
  REPAIR     {rounds: 1-5, model: same|other|m1|m2, template}
                                            while the best fails, ask for a fix
  FINALIZE                                  last step; submits the best candidate

What a strategy can't do: name a model (only slots, bound by the runner to models the run
already allows), carry a prompt (only template IDs from `aiws.templates`), run code, loop
beyond REPAIR.rounds, or declare more calls than the Control-plane cap `max_calls_per_task`.
Unknown operators or fields are rejected.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from aiws.templates import TEMPLATES

MAX_REPAIR_ROUNDS = 5
MAX_PARALLEL = 3
MAX_STEPS = 12
Slot = Literal["m1", "m2"]


class StrategyError(ValueError):
    pass


class _Step(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CallModel(_Step):
    op: Literal["CALL_MODEL"]
    model: Slot
    template: str


class Parallel(_Step):
    op: Literal["PARALLEL"]
    calls: list[CallModel] = Field(min_length=1, max_length=MAX_PARALLEL)


class Verify(_Step):
    op: Literal["VERIFY"]
    tests: Literal["visible", "visible+generated"] = "visible"


class Repair(_Step):
    op: Literal["REPAIR"]
    rounds: StrictInt = Field(ge=1, le=MAX_REPAIR_ROUNDS)
    model: Literal["same", "other", "m1", "m2"]
    template: str


class Finalize(_Step):
    op: Literal["FINALIZE"]


Step = Annotated[Union[CallModel, Parallel, Verify, Repair, Finalize], Field(discriminator="op")]


class Strategy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    version: StrictInt = Field(ge=1)
    description: str = Field(max_length=300)
    max_calls: StrictInt = Field(ge=1)
    steps: list[Step] = Field(min_length=1, max_length=MAX_STEPS)

    def slots(self) -> set[str]:
        out: set[str] = set()
        for s in self.steps:
            calls = s.calls if isinstance(s, Parallel) else (s,)
            for c in calls:
                if isinstance(c, CallModel) or (isinstance(c, Repair) and c.model in ("m1", "m2")):
                    out.add(c.model)
        return out


def worst_case_calls(s: Strategy) -> int:
    n = 0
    for step in s.steps:
        if isinstance(step, CallModel):
            n += 1
        elif isinstance(step, Parallel):
            n += len(step.calls)
        elif isinstance(step, Repair):
            n += step.rounds
    return n


def _check_structure(s: Strategy) -> None:
    if not isinstance(s.steps[-1], Finalize) or any(isinstance(x, Finalize) for x in s.steps[:-1]):
        raise StrategyError("FINALIZE must be the last step, exactly once")
    have_code = have_tests = verified = False
    for i, step in enumerate(s.steps):
        calls = step.calls if isinstance(step, Parallel) else (step,) \
            if isinstance(step, CallModel) else ()
        for c in calls:
            t = TEMPLATES.get(c.template)
            if t is None or t.kind not in ("code", "tests"):
                raise StrategyError(f"step {i}: CALL_MODEL needs a code or tests template, "
                                    f"got {c.template!r}")
            have_code |= t.kind == "code"
            have_tests |= t.kind == "tests"
        if isinstance(step, Verify):
            if not have_code:
                raise StrategyError(f"step {i}: VERIFY before any code was requested")
            if step.tests == "visible+generated" and not have_tests:
                raise StrategyError(f"step {i}: generated tests used but never requested")
            verified = True
        if isinstance(step, Repair):
            t = TEMPLATES.get(step.template)
            if t is None or t.kind != "repair":
                raise StrategyError(f"step {i}: REPAIR needs a repair template, "
                                    f"got {step.template!r}")
            if not verified:
                raise StrategyError(f"step {i}: REPAIR before VERIFY")


def validate_strategy(data: object, *, max_calls_cap: int) -> Strategy:
    if not isinstance(data, dict):
        raise StrategyError("a strategy must be a mapping")
    try:
        s = Strategy.model_validate(data)
    except ValidationError as e:
        raise StrategyError(f"invalid strategy: {e.error_count()} error(s): "
                            f"{e.errors()[0]['loc']} {e.errors()[0]['msg']}") from None
    _check_structure(s)
    need = worst_case_calls(s)
    if need > s.max_calls:
        raise StrategyError(f"{s.id}: steps may make {need} calls, more than max_calls "
                            f"{s.max_calls}")
    if s.max_calls > max_calls_cap:
        raise StrategyError(f"{s.id}: max_calls {s.max_calls} exceeds the policy cap "
                            f"{max_calls_cap}")
    return s


def load_strategy(path: Path | str, *, max_calls_cap: int) -> Strategy:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text())  # safe_load: no Python tags, no objects
    except yaml.YAMLError as e:
        raise StrategyError(f"{path.name}: not plain YAML: {type(e).__name__}") from None
    s = validate_strategy(data, max_calls_cap=max_calls_cap)
    if s.id != path.stem:
        raise StrategyError(f"{path.name}: id {s.id!r} does not match the file name")
    return s


def load_library(root: Path | str, *, max_calls_cap: int) -> dict[str, Strategy]:
    lib = {}
    for p in sorted(Path(root).glob("*.yaml")):
        s = load_strategy(p, max_calls_cap=max_calls_cap)
        lib[s.id] = s
    if not lib:
        raise StrategyError(f"no strategies in {root}")
    return lib


def strategy_sha256(s: Strategy) -> str:
    return hashlib.sha256(json.dumps(s.model_dump(mode="json"), sort_keys=True).encode()
                          ).hexdigest()


def with_repair_rounds(s: Strategy, rounds: int, *, max_calls_cap: int) -> Strategy:
    """Parameter variant (PLAN 6.7 mutation): same steps, every REPAIR set to `rounds`.
    The result is validated again, so a variant can't exceed the cap."""
    data = s.model_dump(mode="json")
    for step in data["steps"]:
        if step["op"] == "REPAIR":
            step["rounds"] = rounds
    data["id"] = f"{s.id}-r{rounds}"[:40]
    data["max_calls"] = 1  # placeholder; set to the real worst case below
    probe = Strategy.model_validate(data)
    data["max_calls"] = worst_case_calls(probe)
    return validate_strategy(data, max_calls_cap=max_calls_cap)
