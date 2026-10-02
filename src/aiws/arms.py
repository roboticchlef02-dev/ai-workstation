"""Experiment arms and the pieces strategies are built from (PLAN 5.2, D-018, D-027).

Since M2 the arms are strategy files (`strategies/`), run by `aiws.interpreter`:
A = `single`, C = `repair` (execute-and-repair, the strong simple baseline), D = `duo`
(two models, pick a passing answer, the other model repairs). The runner runs A and C once
per model (A1, C1, A2, C2) so D is compared with the best single-model arm (M1 reviewer #1).
Prompts live in `aiws.templates`.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiws.benchmark import Task
from aiws.executor import SandboxExecutor
from aiws.metered import CallContext, MeteredClient
from aiws.providers.base import GenerateRequest, Message, ProviderError, Sampling
from aiws.secretguard import SecretLeak
from aiws.templates import REPAIR, SOLVE, SYSTEM, TEMPLATE_VERSION  # noqa: F401  (re-export)

STRATEGY_DIR = Path(__file__).resolve().parents[2] / "strategies"
ARM_STRATEGY = {"A": "single", "C": "repair", "D": "duo"}

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
            except SecretLeak as e:
                # Model code with a key-like placeholder ("Bearer abc…"): the prompt is never
                # sent; this call fails and the run goes on (reviewer #11).
                self.errors.append(f"prompt refused: {e}"[:200])
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
    provider_errors: int = 0  # calls that failed after retries (or were refused)
    trace: list[dict[str, Any]] = field(default_factory=list)
    strategy_id: str = ""
    generated_tests: int = 0  # model-written tests kept after filtering (selftest)
    generated_pass: str = ""  # final code on those tests, "passed/total"


def run_arm(arm: str, task: Task, solvers: list[Solver], ex: SandboxExecutor, ctx: CallContext,
            *, rounds: int, max_calls_cap: int = 20) -> ArmOutcome:
    """M1 entry point: run arm letter A, C or D as its strategy file. `rounds` overrides the
    file's repair rounds (a validated variant) for C and D."""
    from aiws.interpreter import run_strategy, sandbox_verifier
    from aiws.strategy import Repair, load_strategy, with_repair_rounds

    if arm not in ARM_STRATEGY:
        raise ValueError(f"unknown arm {arm!r}")
    s = load_strategy(STRATEGY_DIR / f"{ARM_STRATEGY[arm]}.yaml", max_calls_cap=max_calls_cap)
    file_rounds = {x.rounds for x in s.steps if isinstance(x, Repair)}
    if arm != "A" and file_rounds != {rounds}:
        s = with_repair_rounds(s, rounds, max_calls_cap=max_calls_cap)
    slots = {"m1": solvers[0], "m2": solvers[1] if len(solvers) > 1 else solvers[0]}
    return run_strategy(s, task, slots, sandbox_verifier(ex, task), ctx)
