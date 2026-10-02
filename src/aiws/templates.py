"""Prompt templates: a fixed, versioned library (PLAN 6.7). Strategies refer to templates by
ID and can't write prompts of their own. Changing any text here means a new TEMPLATE_VERSION.

Kinds: "code" asks for a solution, "tests" asks for extra test cases, "repair" asks to fix the
best candidate. The `solve` and `repair` texts are M1's, unchanged (`m1-v1`).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

TEMPLATE_VERSION = "m2-v1"
SYSTEM = "You are an expert Python programmer. You write correct, efficient, self-contained code."
MAX_GENERATED_TESTS = 8

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

EDGE_TESTS = """Write extra test cases for this task. Focus on edge cases and tricky rules in \
the statement that the examples below do not cover.

Task:
{statement}

Signature:
{signature}

Examples (already known; do not repeat them):
{examples}

Reply with one ```json code block holding a list of at most {k} objects of the form \
{{"args": [<argument values>], "expected": <return value>}}. Use JSON values only. Work out \
each expected value carefully from the statement."""

REPAIR_GENERATED = """A solution to this task fails some tests.

Task:
{statement}

Signature:
{signature}

Examples (always correct):
{examples}

Current code:
```python
{code}
```

Failing examples (always correct):
{feedback}

Failing extra tests (written automatically; they may themselves be wrong):
{generated_feedback}

Every example must pass. For each failing extra test, decide from the task statement whether \
the test or the code is right, and change the code only where the statement shows the code is \
wrong. Reply with the complete corrected function in one ```python code block."""


@dataclass(frozen=True)
class Template:
    kind: Literal["code", "tests", "repair"]
    text: str


TEMPLATES: dict[str, Template] = {
    "solve": Template("code", SOLVE),
    "edge_tests": Template("tests", EDGE_TESTS),
    "repair": Template("repair", REPAIR),
    "repair_generated": Template("repair", REPAIR_GENERATED),
}


def template_hashes() -> dict[str, str]:
    """Recorded in every run config, so results name the exact prompt texts used."""
    return {tid: hashlib.sha256((SYSTEM + "\n" + t.text).encode()).hexdigest()[:16]
            for tid, t in sorted(TEMPLATES.items())}
