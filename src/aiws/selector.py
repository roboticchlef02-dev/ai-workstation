"""Which strategy and model to use per task category: Thompson sampling (PLAN 6.9, D-027).

An option is a strategy bound to models, e.g. `repair@1` (repair on model 1) or `duo@1+2`.
For category c and option o, the posterior is Beta(kappa*p + s, kappa*(1-p) + f), where s/f
are o's passes/fails in c and p is o's smoothed pass rate in the *other* categories. So a thin
category borrows strength from the rest (D-022), with the weight of `kappa` observations.

Exploring: sample each posterior, take the highest. Frozen (evaluation): take the highest
posterior mean, never sample, never update. Ties go to fewer max calls, then declared order.
"""

from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


class FrozenError(Exception):
    pass


@dataclass(frozen=True)
class Option:
    strategy_id: str
    models: tuple[int, ...]  # 0-based indices into the run's model list, by slot m1, m2
    max_calls: int

    @property
    def key(self) -> str:
        return f"{self.strategy_id}@{'+'.join(str(i + 1) for i in self.models)}"


class Selector:
    def __init__(self, options: list[Option], *, kappa: float = 2.0, frozen: bool = False):
        if len({o.key for o in options}) != len(options) or not options:
            raise ValueError("options must be non-empty and unique")
        self.options = list(options)
        self.by_key = {o.key: o for o in options}
        self.kappa = kappa
        self.is_frozen = frozen
        self.stats: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])  # [s, f]

    def update(self, category: str, key: str, passed: bool) -> None:
        if self.is_frozen:
            raise FrozenError("frozen selector: no updates during evaluation")
        if key not in self.by_key:
            raise KeyError(f"unknown option {key!r}")
        self.stats[(category, key)][0 if passed else 1] += 1

    def frozen(self) -> Selector:
        f = Selector(self.options, kappa=self.kappa, frozen=True)
        for k, v in self.stats.items():
            f.stats[k] = list(v)
        return f

    def _params(self, category: str, key: str) -> tuple[float, float]:
        s_other = f_other = 0
        for (c, k), (s, f) in self.stats.items():
            if k == key and c != category:
                s_other, f_other = s_other + s, f_other + f
        p = (s_other + 1) / (s_other + f_other + 2)
        s, f = self.stats.get((category, key), (0, 0))
        return self.kappa * p + s, self.kappa * (1 - p) + f

    def posterior_mean(self, category: str, key: str) -> float:
        a, b = self._params(category, key)
        return a / (a + b)

    def pick(self, category: str, rng: random.Random, exclude: frozenset[str] | set[str] = frozenset()
             ) -> Option:
        def score(i_o: tuple[int, Option]) -> tuple[float, int, int]:
            i, o = i_o
            if self.is_frozen:
                v = self.posterior_mean(category, o.key)
            else:
                v = rng.betavariate(*self._params(category, o.key))
            return (v, -o.max_calls, -i)
        candidates = [(i, o) for i, o in enumerate(self.options) if o.key not in exclude]
        if not candidates:
            raise ValueError("every option is excluded")
        return max(candidates, key=score)[1]

    def table(self, categories: list[str]) -> list[dict[str, Any]]:
        """Posterior means per category, for reports."""
        return [{"category": c, **{o.key: round(self.posterior_mean(c, o.key), 3)
                                   for o in self.options},
                 "n": sum(sum(self.stats.get((c, o.key), (0, 0))) for o in self.options)}
                for c in categories]


def split_tasks(tasks: list, seed: int, train_share: float = 0.6) -> tuple[list, list]:
    """Per category, a fixed-seed shuffle; about `train_share` to TRAIN, at least one task on
    each side when a category has two or more, a lone task to TRAIN."""
    by_cat: dict[str, list] = defaultdict(list)
    for t in tasks:
        by_cat[t.category].append(t)
    train, ev = [], []
    for cat in sorted(by_cat):
        group = sorted(by_cat[cat],
                       key=lambda t: hashlib.sha256(f"{seed}:{t.id}".encode()).hexdigest())
        n = len(group)
        k = n if n < 2 else max(1, min(n - 1, round(train_share * n)))
        train += group[:k]
        ev += group[k:]
    order = {t.id: i for i, t in enumerate(tasks)}
    return sorted(train, key=lambda t: order[t.id]), sorted(ev, key=lambda t: order[t.id])
