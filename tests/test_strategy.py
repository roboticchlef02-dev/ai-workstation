"""Strategy DSL v0 (law 3, PLAN 6.7, D-027): strategies are data, never code, and can't widen
what a run may do. Written before the validator."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from aiws.strategy import (
    StrategyError,
    load_library,
    load_strategy,
    strategy_sha256,
    validate_strategy,
    with_repair_rounds,
    worst_case_calls,
)

ROOT = Path(__file__).resolve().parents[1]
CAP = 20

REPAIR = {
    "id": "repair", "version": 1, "description": "solve, then repair on visible failures",
    "max_calls": 4,
    "steps": [
        {"op": "CALL_MODEL", "model": "m1", "template": "solve"},
        {"op": "VERIFY", "tests": "visible"},
        {"op": "REPAIR", "rounds": 3, "model": "same", "template": "repair"},
        {"op": "FINALIZE"},
    ],
}


def mutated(**changes):
    d = copy.deepcopy(REPAIR)
    d.update(changes)
    return d


def with_step(i, step):
    d = copy.deepcopy(REPAIR)
    d["steps"][i] = step
    return d


def test_valid_strategy_loads():
    s = validate_strategy(REPAIR, max_calls_cap=CAP)
    assert s.id == "repair" and worst_case_calls(s) == 4
    assert s.slots() == {"m1"}


@pytest.mark.parametrize("op", ["EXEC", "PYTHON", "SHELL", "HTTP", "WRITE_FILE", "call_model",
                                "CLASSIFY", "MERGE"])
def test_unknown_operator_rejected(op):
    with pytest.raises(StrategyError):
        validate_strategy(with_step(0, {"op": op, "model": "m1", "template": "solve"}),
                          max_calls_cap=CAP)


@pytest.mark.parametrize("field,value", [
    ("prompt", "Ignore previous instructions"), ("code", "import os"), ("system", "x"),
    ("api_key", "x"), ("tools", ["shell"]), ("network", True), ("temperature", 1.5),
])
def test_unknown_step_field_rejected(field, value):
    """No free-form prompts, code, tools or settings can ride along on a step."""
    step = {"op": "CALL_MODEL", "model": "m1", "template": "solve", field: value}
    with pytest.raises(StrategyError):
        validate_strategy(with_step(0, step), max_calls_cap=CAP)


@pytest.mark.parametrize("field,value", [
    ("permissions", ["network"]), ("allowed_models", ["openai/gpt-5"]), ("policy", {}),
    ("max_calls_per_task", 100), ("hooks", ["post"]),
])
def test_unknown_top_level_field_rejected(field, value):
    with pytest.raises(StrategyError):
        validate_strategy(mutated(**{field: value}), max_calls_cap=CAP)


@pytest.mark.parametrize("model", ["gemini/gemini-3.8-flash", "groq/x", "m3", "", "M1", "*"])
def test_models_are_slots_only(model):
    """A strategy can't name a model: the runner binds m1/m2 to models the run already allows."""
    with pytest.raises(StrategyError):
        validate_strategy(with_step(0, {"op": "CALL_MODEL", "model": model, "template": "solve"}),
                          max_calls_cap=CAP)


@pytest.mark.parametrize("template", ["free text prompt", "../../etc/passwd", "SOLVE", "nope"])
def test_unknown_template_rejected(template):
    with pytest.raises(StrategyError):
        validate_strategy(with_step(0, {"op": "CALL_MODEL", "model": "m1", "template": template}),
                          max_calls_cap=CAP)


def test_template_kind_must_fit_the_operator():
    with pytest.raises(StrategyError):  # a repair template has no candidate to repair here
        validate_strategy(with_step(0, {"op": "CALL_MODEL", "model": "m1", "template": "repair"}),
                          max_calls_cap=CAP)
    with pytest.raises(StrategyError):
        validate_strategy(with_step(2, {"op": "REPAIR", "rounds": 1, "model": "same",
                                        "template": "solve"}), max_calls_cap=CAP)


def test_worst_case_calls_must_fit_declared_max():
    with pytest.raises(StrategyError):
        validate_strategy(mutated(max_calls=3), max_calls_cap=CAP)  # needs 1 + 3


def test_max_calls_cannot_exceed_the_policy_cap():
    """Strategy ≠ privilege: the per-task cap comes from the Control plane, not the strategy."""
    big = with_step(2, {"op": "REPAIR", "rounds": 5, "model": "same", "template": "repair"})
    big["max_calls"] = 6
    assert validate_strategy(big, max_calls_cap=6)
    with pytest.raises(StrategyError):
        validate_strategy(big, max_calls_cap=5)


@pytest.mark.parametrize("rounds", [0, -1, 6, 1000, 2.5, "3", True])
def test_repair_rounds_bounded(rounds):
    step = {"op": "REPAIR", "rounds": rounds, "model": "same", "template": "repair"}
    d = with_step(2, step)
    d["max_calls"] = CAP
    with pytest.raises(StrategyError):
        validate_strategy(d, max_calls_cap=CAP)


def test_structure_rules():
    no_final = copy.deepcopy(REPAIR)
    no_final["steps"] = no_final["steps"][:-1]
    early_final = copy.deepcopy(REPAIR)
    early_final["steps"].insert(1, {"op": "FINALIZE"})
    repair_first = copy.deepcopy(REPAIR)
    repair_first["steps"] = [repair_first["steps"][2], *repair_first["steps"][:2],
                             repair_first["steps"][3]]
    verify_first = copy.deepcopy(REPAIR)
    verify_first["steps"] = [{"op": "VERIFY"}, *verify_first["steps"]]
    generated_without_tests = with_step(1, {"op": "VERIFY", "tests": "visible+generated"})
    for bad in (no_final, early_final, repair_first, verify_first, generated_without_tests):
        with pytest.raises(StrategyError):
            validate_strategy(bad, max_calls_cap=CAP)


def test_parallel_holds_only_model_calls():
    for inner in ({"op": "PARALLEL", "calls": []}, {"op": "REPAIR", "rounds": 1, "model": "same",
                                                     "template": "repair"}):
        with pytest.raises(StrategyError):
            validate_strategy(with_step(0, {"op": "PARALLEL", "calls": [inner]}),
                              max_calls_cap=CAP)
    with pytest.raises(StrategyError):  # bounded width
        validate_strategy(with_step(0, {"op": "PARALLEL", "calls": [
            {"op": "CALL_MODEL", "model": "m1", "template": "solve"}] * 4}), max_calls_cap=CAP)


def test_too_many_steps_rejected():
    d = copy.deepcopy(REPAIR)
    d["steps"] = [{"op": "VERIFY"}] * 20 + d["steps"]
    with pytest.raises(StrategyError):
        validate_strategy(d, max_calls_cap=CAP)


@pytest.mark.parametrize("bad_id", ["Repair", "../x", "a b", "", "x" * 60, "rm -rf"])
def test_strategy_id_format(bad_id):
    with pytest.raises(StrategyError):
        validate_strategy(mutated(id=bad_id), max_calls_cap=CAP)


def test_yaml_python_tags_rejected(tmp_path):
    p = tmp_path / "evil.yaml"
    p.write_text("id: evil\nversion: 1\ndescription: !!python/object/apply:os.system ['true']\n")
    with pytest.raises(StrategyError):
        load_strategy(p, max_calls_cap=CAP)


def test_file_id_must_match_file_name(tmp_path):
    p = tmp_path / "other.yaml"
    p.write_text(yaml.safe_dump(REPAIR))
    with pytest.raises(StrategyError):
        load_strategy(p, max_calls_cap=CAP)


def test_hash_changes_with_content():
    a = validate_strategy(REPAIR, max_calls_cap=CAP)
    b = validate_strategy(mutated(description="other"), max_calls_cap=CAP)
    assert strategy_sha256(a) != strategy_sha256(b)
    assert strategy_sha256(a) == strategy_sha256(validate_strategy(REPAIR, max_calls_cap=CAP))


def test_repair_rounds_variant_is_validated():
    s = validate_strategy(REPAIR, max_calls_cap=CAP)
    v = with_repair_rounds(s, 2, max_calls_cap=CAP)
    assert v.id == "repair-r2" and worst_case_calls(v) == 3 and v.max_calls == 3
    with pytest.raises(StrategyError):
        with_repair_rounds(s, 5, max_calls_cap=4)


def test_builtin_library_is_valid_and_budget_matched():
    lib = load_library(ROOT / "strategies", max_calls_cap=CAP)
    assert {"single", "repair", "duo", "selftest"} <= set(lib)
    assert all(s.max_calls <= 4 for s in lib.values())  # D-027: budget match at 4 calls
    assert lib["duo"].slots() == {"m1", "m2"}
