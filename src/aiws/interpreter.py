"""Runs a validated strategy (aiws.strategy) on one task (D-027).

Fixed rules, not part of any strategy:
- Selection: candidates rank by (all visible examples pass, visible passes, generated tests
  passed); ties go to the earlier candidate. A repair replaces the best only if it ranks at
  least as high, so a repair can't trade a visible example for generated tests.
- Generated tests are untrusted model output: parsed as JSON, filtered, capped, and run only
  in the sandbox through the same verifier as the visible examples. They never reach the
  evaluator, and the tests prompt never shows candidate code.
- The interpreter re-checks the worst-case call count before the first call (defense in depth;
  the validator already did) and stops at the strategy's `max_calls` whatever happens.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from aiws.arms import ArmOutcome, Solver, examples_text, extract_code
from aiws.benchmark import Case, Task, _finite, check, run_cases
from aiws.budget import BudgetExceeded
from aiws.executor import SandboxExecutor
from aiws.metered import CallContext
from aiws.strategy import CallModel, Parallel, Repair, Strategy, Verify, worst_case_calls
from aiws.templates import MAX_GENERATED_TESTS, TEMPLATES

# (code, cases) -> (number passed, failure messages). Runs code only in the sandbox.
Verifier = Callable[[str, list[Case]], tuple[int, list[str]]]
MAX_FEEDBACK = 3
_JSON_FENCE = re.compile(r"```(?:json)?[ \t]*\n(.*?)```", re.S | re.I)
_MAX_REPLY_CHARS = 100_000
_MAX_TEST_CHARS = 2_000


class StrategyRunError(RuntimeError):
    pass


def sandbox_verifier(ex: SandboxExecutor, task: Task) -> Verifier:
    def verify(code: str, cases: list[Case]) -> tuple[int, list[str]]:
        results, err = run_cases(ex, task.entry_point, code, [c.args for c in cases])
        verdicts = check(results, cases, task.compare, task.entry_point)
        fails = [err] if results is None else [m for ok, m in verdicts if not ok]
        return sum(ok for ok, _ in verdicts), fails
    return verify


@dataclass
class Cand:
    code: str
    model_id: str
    slot: str
    n_pass: int = 0
    n_total: int = 0
    feedback: list[str] = field(default_factory=list)
    gen_pass: int = 0
    gen_total: int = 0
    gen_feedback: list[str] = field(default_factory=list)
    checked: tuple[str, int] | None = None  # (tests mode, number of generated tests) last run

    @property
    def passes(self) -> bool:
        return bool(self.code) and self.n_total > 0 and self.n_pass == self.n_total

    def rank(self) -> tuple[bool, int, int]:
        return (self.passes, self.n_pass, self.gen_pass)


def _kind(v: Any) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    return {str: "str", list: "list", dict: "dict", type(None): "null"}.get(type(v), "other")


def parse_generated_tests(text: str, task: Task, k: int = MAX_GENERATED_TESTS) -> list[Case]:
    """Model-written tests -> at most k Cases. Anything odd is dropped, never raised:
    wrong shape, extra keys, args equal to a visible example's, a different argument count
    or result kind than the visible examples, non-finite numbers, duplicates, oversize."""
    try:
        return _parse_generated(text[:_MAX_REPLY_CHARS], task, k)
    except (RecursionError, ValueError, TypeError, OverflowError):
        return []


def _parse_generated(text: str, task: Task, k: int) -> list[Case]:
    data = None
    for block in reversed(_JSON_FENCE.findall(text) or [text]):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, list):
            break
    if not isinstance(data, list):
        return []
    visible = {json.dumps(c.args, sort_keys=True) for c in task.visible_tests}
    arity = {len(c.args) for c in task.visible_tests}
    kinds = {_kind(c.expected) for c in task.visible_tests}
    out: list[Case] = []
    seen: set[str] = set()
    for item in data:
        if len(out) >= k:
            break
        if not isinstance(item, dict) or set(item) != {"args", "expected"} \
                or not isinstance(item["args"], list):
            continue
        key = json.dumps(item["args"], sort_keys=True)
        if len(key) + len(json.dumps(item["expected"])) > _MAX_TEST_CHARS:
            continue
        if key in visible or key in seen or (arity and len(item["args"]) not in arity):
            continue
        if len(kinds) == 1 and _kind(item["expected"]) not in kinds:
            continue
        if not _finite(item["expected"]) or not _finite(item["args"]):
            continue
        seen.add(key)
        out.append(Case(args=item["args"], expected=item["expected"]))
    return out


class _Run:
    def __init__(self, strategy: Strategy, task: Task, slots: dict[str, Solver],
                 verifier: Verifier, ctx: CallContext):
        self.s, self.task, self.slots, self.verifier, self.ctx = strategy, task, slots, verifier, ctx
        self.cands: list[Cand] = []
        self.best: Cand | None = None
        self.generated: list[Case] = []
        self.mode = "visible"
        self.calls = 0
        self.repairs = 0
        self.trace: list[dict[str, Any]] = []

    # -- model calls -------------------------------------------------------------------
    def _fmt(self) -> dict[str, str]:
        t = self.task
        return {"statement": t.statement, "signature": t.signature, "examples": examples_text(t)}

    def _ask(self, slot: str, prompt: str) -> str:
        if self.calls >= self.s.max_calls:
            raise StrategyRunError("max_calls reached")  # unreachable for a validated strategy
        self.calls += 1
        return self.slots[slot].ask(prompt, self.ctx) or ""

    def call(self, c: CallModel) -> None:
        tpl = TEMPLATES[c.template]
        if tpl.kind == "tests":
            text = self._ask(c.model, tpl.text.format(**self._fmt(), k=MAX_GENERATED_TESTS))
            new = parse_generated_tests(text, self.task)
            known = {json.dumps(x.args, sort_keys=True) for x in self.generated}
            self.generated += [x for x in new if json.dumps(x.args, sort_keys=True) not in known]
            self.generated = self.generated[:MAX_GENERATED_TESTS]
            self.trace.append({"step": "tests", "model": self.slots[c.model].model_id,
                               "generated": len(self.generated)})
            return
        text = self._ask(c.model, tpl.text.format(**self._fmt()))
        self.cands.append(Cand(code=extract_code(text), model_id=self.slots[c.model].model_id,
                               slot=c.model))

    # -- verification ------------------------------------------------------------------
    def check(self, c: Cand) -> Cand:
        gen = self.generated if self.mode == "visible+generated" else []
        if c.checked == (self.mode, len(gen)):
            return c
        c.n_total = len(self.task.visible_tests)
        c.gen_total = len(gen)
        if not c.code:
            c.n_pass = c.gen_pass = 0
            c.feedback = ["No code was found in the reply. Reply with one ```python code block."]
            c.gen_feedback = []
        else:
            if c.checked is None:  # visible results don't change; run them once
                c.n_pass, c.feedback = self.verifier(c.code, list(self.task.visible_tests))
            c.gen_pass, c.gen_feedback = self.verifier(c.code, gen) if gen else (0, [])
        c.checked = (self.mode, len(gen))
        return c

    def verify(self, v: Verify) -> None:
        self.mode = v.tests
        fresh = [c for c in self.cands if c.checked is None]
        for c in self.cands:
            self.check(c)
        for c in fresh:
            self._note("solve", c)
        if self.cands:
            self.best = max(self.cands, key=Cand.rank)  # max keeps the first of equals
            if self.mode == "visible+generated" and not fresh:
                self._note("verify", self.best)

    def failing(self) -> bool:
        b = self.best
        return b is None or not b.passes or (self.mode == "visible+generated"
                                             and b.gen_pass < b.gen_total)

    def repair(self, r: Repair) -> None:
        used = 0
        while self.failing() and used < r.rounds and self.best is not None:
            used += 1
            self.repairs += 1
            b = self.best
            slot = {"same": b.slot, "other": "m2" if b.slot == "m1" else "m1"}.get(r.model, r.model)
            prompt = TEMPLATES[r.template].text.format(
                **self._fmt(), code=b.code or "# (no code)",
                feedback="\n".join(f"- {m}" for m in b.feedback[:MAX_FEEDBACK]) or "- (none)",
                generated_feedback="\n".join(f"- {m}" for m in b.gen_feedback[:MAX_FEEDBACK])
                or "- (none)")
            c = Cand(code=extract_code(self._ask(slot, prompt)),
                     model_id=self.slots[slot].model_id, slot=slot)
            self.cands.append(self.check(c))
            self._note(f"repair{self.repairs}", c)
            if c.rank() >= b.rank():
                self.best = c

    def _note(self, step: str, c: Cand) -> None:
        entry: dict[str, Any] = {"step": step, "model": c.model_id,
                                 "visible": f"{c.n_pass}/{c.n_total}"}
        if self.mode == "visible+generated":
            entry["generated"] = f"{c.gen_pass}/{c.gen_total}"
        self.trace.append(entry)


def run_strategy(strategy: Strategy, task: Task, slots: dict[str, Solver], verifier: Verifier,
                 ctx: CallContext) -> ArmOutcome:
    if worst_case_calls(strategy) > strategy.max_calls:
        raise StrategyRunError(f"{strategy.id}: steps exceed max_calls")
    missing = strategy.slots() - set(slots)
    if strategy.slots() and "other" in {getattr(x, "model", "") for x in strategy.steps}:
        missing |= {"m1", "m2"} - set(slots)
    if missing:
        raise StrategyRunError(f"{strategy.id}: unbound model slots {sorted(missing)}")
    run = _Run(strategy, task, slots, verifier, ctx)
    solvers = list({id(s): s for s in slots.values()}.values())
    calls_before = sum(s.calls for s in solvers)
    errors_before = sum(len(s.errors) for s in solvers)
    stopped = ""
    try:
        for step in strategy.steps:
            if isinstance(step, CallModel):
                run.call(step)
            elif isinstance(step, Parallel):
                for c in step.calls:
                    run.call(c)
            elif isinstance(step, Verify):
                run.verify(step)
            elif isinstance(step, Repair):
                run.repair(step)
    except BudgetExceeded as e:
        stopped = f"budget:{e.level}"
        if e.level in ("run", "experiment", "global"):
            raise
    except StrategyRunError as e:
        stopped = str(e)
    best = run.best or Cand(code="", model_id=slots["m1"].model_id, slot="m1")
    gen = f"{best.gen_pass}/{best.gen_total}" if run.mode == "visible+generated" else ""
    return ArmOutcome(code=best.code, visible_pass=best.passes,
                      model_calls=sum(s.calls for s in solvers) - calls_before,
                      rounds_used=run.repairs, winner_model=best.model_id, stopped=stopped,
                      provider_errors=sum(len(s.errors) for s in solvers) - errors_before,
                      trace=run.trace, strategy_id=strategy.id,
                      generated_tests=len(run.generated), generated_pass=gen)
