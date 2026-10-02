"""M2 learning plane (D-027): experience log, per-category Thompson selector, TRAIN/EVAL split.
Written before src/aiws/{experience,selector}.py."""

from __future__ import annotations

import random

import pytest

from aiws.benchmark import Case, Task
from aiws.experience import ExperienceLog, ExperienceRefused, ExperienceRow
from aiws.secretguard import SecretLeak
from aiws.selector import FrozenError, Option, Selector, split_tasks

OPTS = [Option("single", (0,), 1), Option("repair", (0,), 4), Option("duo", (0, 1), 4)]


def row(**kw) -> dict:
    base = dict(run_id="r1", pool="TRAIN", task_id="t1", category="arrays", difficulty=2,
                option="repair@1", strategy_id="repair", strategy_version=1,
                strategy_sha256="ab" * 32, models=["groq/m"], passed=True, hidden="5/5",
                visible_pass=True, model_calls=2, rounds_used=1, generated_tests=0,
                shadow_usd=0.0, evaluator_version="0.2.0", benchmark_sha256="cd" * 32,
                template_version="m2-v1", code_sha256="ef" * 32)
    base.update(kw)
    return base


# --- experience log ------------------------------------------------------------------------

def test_log_round_trip(tmp_path):
    log = ExperienceLog(tmp_path / "x.sqlite")
    log.write(ExperienceRow(**row()))
    log.write(ExperienceRow(**row(task_id="t2", passed=False)))
    rows = log.rows()
    assert [r.task_id for r in rows] == ["t1", "t2"] and rows[1].passed is False


@pytest.mark.parametrize("pool", ["EVAL", "VALIDATION", "HELD_OUT", "SEED", "train", ""])
def test_log_accepts_train_rows_only(tmp_path, pool):
    """Held-out and evaluation outcomes never enter the learning plane (PLAN 5.1)."""
    log = ExperienceLog(tmp_path / "x.sqlite")
    with pytest.raises((ExperienceRefused, ValueError)):
        log.write(ExperienceRow(**row(pool=pool)))
    assert log.rows() == []


def test_frozen_log_refuses_writes(tmp_path):
    log = ExperienceLog(tmp_path / "x.sqlite")
    log.write(ExperienceRow(**row()))
    frozen = ExperienceLog(tmp_path / "x.sqlite", frozen=True)
    with pytest.raises(ExperienceRefused):
        frozen.write(ExperienceRow(**row(task_id="t9")))
    assert len(frozen.rows()) == 1


def test_log_refuses_secrets_and_unknown_fields(tmp_path):
    log = ExperienceLog(tmp_path / "x.sqlite")
    with pytest.raises(SecretLeak):
        log.write(ExperienceRow(**row(task_id="AIza" + "K" * 35)))
    with pytest.raises(ValueError):
        ExperienceRow(**row(code="def f(): pass"))  # code text is not stored, only its hash
    with pytest.raises(ValueError):
        ExperienceRow(**{k: v for k, v in row().items() if k != "strategy_sha256"})
    assert log.rows() == []


# --- selector ------------------------------------------------------------------------------

def test_frozen_selector_is_greedy_and_read_only():
    sel = Selector(OPTS)
    for _ in range(5):
        sel.update("arrays", "single@1", True)
        sel.update("arrays", "repair@1", False)
    frozen = sel.frozen()
    picks = {frozen.pick("arrays", random.Random(i)).key for i in range(20)}
    assert picks == {"single@1"}
    with pytest.raises(FrozenError):
        frozen.update("arrays", "single@1", True)


def test_ties_go_to_fewer_calls_then_declared_order():
    sel = Selector(OPTS).frozen()
    assert sel.pick("arrays", random.Random(0)).key == "single@1"  # no data: all equal
    sel2 = Selector([Option("repair", (0,), 4), Option("duo", (0, 1), 4)]).frozen()
    assert sel2.pick("x", random.Random(0)).key == "repair@1"


def test_thompson_is_reproducible_with_a_seed():
    sel = Selector(OPTS)
    a = [sel.pick("graphs", random.Random(7)).key for _ in range(3)]
    b = [sel.pick("graphs", random.Random(7)).key for _ in range(3)]
    assert a == b


def test_empty_category_borrows_the_pooled_rate():
    """D-022: a thin category starts from the other categories' rate, not from zero."""
    sel = Selector(OPTS)
    for cat in ("arrays", "strings", "graphs"):
        for _ in range(6):
            sel.update(cat, "duo@1+2", True)
            sel.update(cat, "single@1", False)
    assert sel.frozen().pick("never_seen", random.Random(0)).key == "duo@1+2"
    m = sel.posterior_mean("never_seen", "duo@1+2")
    assert 0.5 < m < 1.0  # pulled up by the pooled prior, but only with strength kappa


def test_category_evidence_overrides_the_pool():
    sel = Selector(OPTS)
    for cat in ("arrays", "strings"):
        for _ in range(6):
            sel.update(cat, "duo@1+2", True)
    for _ in range(8):
        sel.update("graphs", "duo@1+2", False)
        sel.update("graphs", "repair@1", True)
    assert sel.frozen().pick("graphs", random.Random(0)).key == "repair@1"


def test_thompson_converges_on_the_best_option():
    rng = random.Random(1)
    truth = {"single@1": 0.2, "repair@1": 0.5, "duo@1+2": 0.8}
    sel = Selector(OPTS)
    for _ in range(300):
        o = sel.pick("dp", rng)
        sel.update("dp", o.key, rng.random() < truth[o.key])
    late = [sel.pick("dp", rng).key for _ in range(200)]
    assert late.count("duo@1+2") / len(late) > 0.8
    assert sel.frozen().pick("dp", rng).key == "duo@1+2"


def test_unknown_option_refused():
    with pytest.raises(KeyError):
        Selector(OPTS).update("arrays", "rm -rf@1", True)


def test_option_keys():
    assert [o.key for o in OPTS] == ["single@1", "repair@1", "duo@1+2"]


# --- split ---------------------------------------------------------------------------------

def _task(tid, cat):
    return Task(id=tid, category=cat, difficulty=1, entry_point="f", signature="def f():",
                statement="s", visible_tests=[Case(args=[], expected=1)])


def test_split_is_disjoint_stable_and_covers_categories():
    tasks = [_task(f"{c}-{i}", c) for c, n in (("a", 2), ("b", 3), ("c", 5), ("d", 1))
             for i in range(n)]
    train, ev = split_tasks(tasks, seed=1)
    assert not {t.id for t in train} & {t.id for t in ev}
    assert len(train) + len(ev) == len(tasks)
    for c in ("a", "b", "c"):
        assert any(t.category == c for t in train) and any(t.category == c for t in ev)
    assert [t.category for t in train].count("c") == 3  # 60% of 5
    assert all(t.category != "d" for t in ev)  # a lone task goes to TRAIN
    assert split_tasks(tasks, seed=1) == (train, ev)
    assert split_tasks(tasks, seed=2) != (train, ev)
