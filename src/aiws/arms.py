"""Experiment arms for M1 (PLAN 5.2, D-018).

A  single shot: one call, no execution.
C  execute-and-repair: one model; run the visible examples; on failure, show the model the
   failures and let it fix the code (up to `rounds` repairs). The strong simple baseline.
D  simple two-model workstation: two solvers answer independently; visible examples pick a
   passing answer; if none passes, the *other* model repairs the best candidate, alternating.

All arms see the same statement and visible examples and run the same executor. A and C
make at most 1 and 1+rounds calls; D makes at most 2+rounds. Prompts come from versioned
templates below; changing a template means a new TEMPLATE_VERSION.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from aiws.benchmark import Task, check, run_cases
from aiws.budget import BudgetExceeded
from aiws.executor import SandboxExecutor
from aiws.metered import CallContext, MeteredClient
from aiws.providers.base import GenerateRequest, Message, ProviderError, Sampling

TEMPLATE_VERSION = "m1-v1"
SYSTEM = "You are an expert Python programmer. You write correct, efficient, self-contained code."

SOLVE = """Write a Python function for this task.

Task:
{statement}

Signature:
{signature}

Examples:
{examples}

Reply with the complete function in one ```python code block. You may add imports and helper \
functions. Do not read input and do not print; only define the function."""

REPAIR = """A solution to this task fails some of the examples.

Task:
{statement}

Signature:
{signature}

Examples:
{examples}

Current code:
```python
{code}
```

Failures:
{feedback}

Fix the code so every example passes. Reply with the complete corrected function in one \
```python code block."""

_FENCE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.S | re.I)


def extract_code(text: str) -> str:
    """Last fenced code block that defines something; else the whole text if it has a def."""
    blocks = [b for b in _FENCE.findall(text) if "def " in b or "import " in b]
    if blocks:
        return blocks[-1].strip() + "\n"
    return text.strip() + "\n" if "def " in text else ""


def examples_text(task: Task) -> str:
    import json
    return "\n".join(f"{task.entry_point}({', '.join(json.dumps(a) for a in c.args)}) == "
                     f"{json.dumps(c.expected)}" for c in task.visible_tests)


@dataclass
class Candidate:
    code: str
    model_id: str
    n_pass: int = 0
    n_total: int = 0
    feedback: list[str] = field(default_factory=list)

    @property
    def passes(self) -> bool:
        return bool(self.code) and self.n_total > 0 and self.n_pass == self.n_total


def verify(ex: SandboxExecutor, task: Task, cand: Candidate) -> Candidate:
    """Run the visible examples (never hidden tests) and record failures as feedback."""
    cand.n_total = len(task.visible_tests)
    if not cand.code:
        cand.feedback = ["No code was found in the reply. Reply with one ```python code block."]
        return cand
    results, err = run_cases(ex, task.entry_point, cand.code, [c.args for c in task.visible_tests])
    verdicts = check(results, task.visible_tests, task.compare, task.entry_point)
    cand.n_pass = sum(ok for ok, _ in verdicts)
    cand.feedback = [err] if results is None else [m for ok, m in verdicts if not ok]
    return cand


class Solver:
    """One model behind the metered client, with free-tier pacing and retry on rate limits."""

    def __init__(self, client: MeteredClient, model_id: str, *, max_output_tokens: int = 8192,
                 sampling: Sampling | None = None, min_interval_s: float = 0.0,
                 max_retries: int = 5, backoff_s: float = 5.0):
        self.client, self.model_id = client, model_id
        self.max_output_tokens = max_output_tokens
        self.sampling = sampling or Sampling(temperature=0.2)
        self.min_interval_s, self.max_retries, self.backoff_s = min_interval_s, max_retries, backoff_s
        self._last = 0.0
        self.calls = 0
        self.errors: list[str] = []

    def ask(self, prompt: str, ctx: CallContext) -> str | None:
        req = GenerateRequest(model_id=self.model_id, system=SYSTEM,
                              messages=(Message(role="user", content=prompt),),
                              max_output_tokens=self.max_output_tokens, sampling=self.sampling)
        for attempt in range(self.max_retries + 1):
            wait = self._last + self.min_interval_s - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                text = self.client.generate(req, ctx).text
                self.calls += 1
                return text
            except ProviderError as e:
                if e.retryable and attempt < self.max_retries:  # R9: retry, never a task failure
                    time.sleep(self.backoff_s * 2 ** attempt)
                    continue
                self.calls += 1  # a failed call still counts against the arm
                self.errors.append(str(e)[:200])
                return None
        return None


@dataclass
class ArmOutcome:
    code: str
    visible_pass: bool
    model_calls: int
    rounds_used: int
    winner_model: str
    stopped: str = ""  # why the arm stopped early (budget), if it did
    trace: list[dict[str, Any]] = field(default_factory=list)


def _ask(solver: Solver, prompt: str, ctx: CallContext) -> Candidate:
    text = solver.ask(prompt, ctx)
    return Candidate(code=extract_code(text or ""), model_id=solver.model_id)


def _fmt(task: Task) -> dict[str, str]:
    return {"statement": task.statement, "signature": task.signature,
            "examples": examples_text(task)}


def _repair_prompt(task: Task, cand: Candidate) -> str:
    return REPAIR.format(**_fmt(task), code=cand.code or "# (no code)",
                         feedback="\n".join(f"- {m}" for m in cand.feedback[:3]))


def run_arm(arm: str, task: Task, solvers: list[Solver], ex: SandboxExecutor, ctx: CallContext,
            *, rounds: int) -> ArmOutcome:
    calls_before = sum(s.calls for s in solvers)
    trace: list[dict[str, Any]] = []
    stopped = ""
    best: Candidate | None = None
    used = 0

    def note(step: str, c: Candidate) -> None:
        trace.append({"step": step, "model": c.model_id, "visible": f"{c.n_pass}/{c.n_total}"})

    try:
        if arm == "A":
            best = verify(ex, task, _ask(solvers[0], SOLVE.format(**_fmt(task)), ctx))
            note("solve", best)
        elif arm == "C":
            best = verify(ex, task, _ask(solvers[0], SOLVE.format(**_fmt(task)), ctx))
            note("solve", best)
            while not best.passes and used < rounds:
                used += 1
                best = verify(ex, task, _ask(solvers[0], _repair_prompt(task, best), ctx))
                note(f"repair{used}", best)
        elif arm == "D":
            pair = solvers[:2] if len(solvers) >= 2 else [solvers[0], solvers[0]]
            cands = []
            for s in pair:
                c = verify(ex, task, _ask(s, SOLVE.format(**_fmt(task)), ctx))
                note("solve", c)
                cands.append(c)
            best = max(cands, key=lambda c: (c.passes, c.n_pass))  # ties: first solver
            while not best.passes and used < rounds:
                used += 1
                other = pair[1] if best.model_id == pair[0].model_id else pair[0]
                c = verify(ex, task, _ask(other, _repair_prompt(task, best), ctx))
                note(f"repair{used}", c)
                if (c.passes, c.n_pass) >= (best.passes, best.n_pass):
                    best = c
        else:
            raise ValueError(f"unknown arm {arm!r}")
    except BudgetExceeded as e:
        stopped = f"budget:{e.level}"
        if e.level in ("run", "experiment", "global"):
            raise
    best = best or Candidate(code="", model_id=solvers[0].model_id)
    return ArmOutcome(code=best.code, visible_pass=best.passes,
                      model_calls=sum(s.calls for s in solvers) - calls_before,
                      rounds_used=used, winner_model=best.model_id, stopped=stopped, trace=trace)
