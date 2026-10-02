"""M2 learning run: TRAIN stream with a per-category bandit, then frozen warm vs cold on EVAL.

  python -m aiws.learn --models groq:allam-2-7b --strategies single,repair,selftest \
                       --confirm-spend

1. Seed tasks are split per category (fixed seed) into TRAIN and EVAL (D-027).
2. TRAIN: for each task (random order), the selector picks `--per-task` options by Thompson
   sampling; each runs; the evaluator's verdict goes to the experience log and the selector.
3. Freeze. EVAL: every option runs once on every task (random order per task, A11). Policies
   are scored on those same runs, paired by task: cold = the default option (`repair` on
   model 1, the strong simple baseline), warm = the frozen selector's pick per category.
EVAL outcomes never enter the experience log or the selector.

Safety as in aiws.run: --confirm-spend for any non-zero estimate, L3 or nothing, every call
metered. Exploratory only (D-018): builder-written seed tasks, small n.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiws import arms as arms_mod
from aiws.arms import Solver
from aiws.benchmark import Task, load_tasks
from aiws.budget import BudgetExceeded, Ledger, load_caps, spend_preflight
from aiws.evaluator import EvaluatorClient
from aiws.executor import SandboxExecutor
from aiws.experience import ExperienceLog, ExperienceRow
from aiws.fingerprint import fingerprint
from aiws.interpreter import run_strategy, sandbox_verifier
from aiws.metered import CallContext, MeteredClient
from aiws.prices import PriceTable
from aiws.providers.base import GenerateRequest, Message, ModelProvider
from aiws.run import DEFAULT_INTERVAL, ROOT, _token_totals, make_provider
from aiws.secretguard import assert_no_secret, redact
from aiws.selector import Option, Selector, split_tasks
from aiws.strategy import Strategy, load_library, strategy_sha256
from aiws.telemetry import Telemetry
from aiws.templates import TEMPLATE_VERSION, template_hashes

COLD = "repair@1"


def protected_dirs() -> list[Path]:
    lines = (ROOT / "configs" / "protected_paths.txt").read_text().splitlines()
    return [(ROOT / ln.strip().rstrip("/")).resolve() for ln in lines
            if ln.strip() and not ln.startswith("#") and "*" not in ln]


def refuse_protected(path: Path) -> None:
    """The learning plane never opens held-out or secret paths (PLAN 5.5, CLAUDE.md)."""
    p = path.resolve()
    for d in protected_dirs():
        if p == d or p.is_relative_to(d) or "held_out" in p.parts:
            raise SystemExit(f"refusing protected path {path}")


def make_options(lib: dict[str, Strategy], n_models: int) -> list[Option]:
    opts = []
    for sid, s in lib.items():
        two = "m2" in s.slots() or any(getattr(x, "model", "") == "other" for x in s.steps)
        if two:
            opts.append(Option(sid, (0, 1) if n_models >= 2 else (0, 0), s.max_calls))
        else:
            opts += [Option(sid, (i,), s.max_calls) for i in range(n_models)]
    return opts


def estimate_usd(train: list[Task], ev: list[Task], options: list[Option], per_task: int,
                 providers: list[tuple[ModelProvider, str]], prices: PriceTable,
                 max_out: int) -> float:
    """Worst case: every call at the dearest model with the full output allowance."""
    today = datetime.now(timezone.utc).date()
    worst = max(o.max_calls for o in options)
    total = 0.0
    for phase, tasks in (("train", train), ("eval", ev)):
        for t in tasks:
            prompt = arms_mod.SOLVE.format(statement=t.statement, signature=t.signature,
                                           examples=arms_mod.examples_text(t)) * 2
            per_call = max(p.estimate_cost_usd(GenerateRequest(
                model_id=mid, system=arms_mod.SYSTEM, max_output_tokens=max_out,
                messages=(Message(role="user", content=prompt),)), prices, on=today)
                for p, mid in providers)
            calls = per_task * worst if phase == "train" else sum(o.max_calls for o in options)
            total += calls * per_call
    return total


def mcnemar_p(b: int, c: int) -> float:
    """Exact two-sided McNemar p-value from the discordant counts."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def run_learning(*, models: list[str], strategies: list[str] | None, benchmark: Path,
                 split_seed: int, seed: int, per_task: int, confirm_spend: bool, pool: str,
                 max_out: int, out_dir: Path, state_dir: Path, interval: float | None = None,
                 providers: list[tuple[ModelProvider, str]] | None = None,
                 limit_train: int | None = None, limit_eval: int | None = None,
                 log=print) -> dict[str, Any]:
    refuse_protected(benchmark)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-learn-s{seed}"
    caps = load_caps()
    prices = PriceTable.load()
    lib_all = load_library(ROOT / "strategies", max_calls_cap=caps.max_calls_per_task)
    lib = {k: lib_all[k] for k in (strategies or sorted(lib_all))}
    state_dir.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(state_dir / "ledger.sqlite", caps)
    telemetry = Telemetry(state_dir / "telemetry.sqlite")
    experience = ExperienceLog(state_dir / "experience.sqlite")
    train, ev_tasks = split_tasks(load_tasks(benchmark), seed=split_seed)
    train, ev_tasks = train[:limit_train or None], ev_tasks[:limit_eval or None]
    providers = providers or [make_provider(m) for m in models]
    options = make_options(lib, len(providers))
    if COLD not in {o.key for o in options}:
        raise SystemExit(f"the cold baseline {COLD} needs the `repair` strategy")
    per_task = max(1, min(per_task, len(options)))

    est = estimate_usd(train, ev_tasks, options, per_task, providers, prices, max_out)
    log(spend_preflight(est, confirm_spend=confirm_spend, caps=caps, ledger=ledger))
    ex = SandboxExecutor()
    if ex.isolation_level() != "L3":
        raise SystemExit(f"refusing to run: sandbox is {ex.isolation_level()} ({ex.why_not_l3()})")
    solvers = []
    for prov, mid in providers:
        client = MeteredClient(prov, ledger=ledger, prices=prices, telemetry=telemetry)
        gap = DEFAULT_INTERVAL.get(prov.name, 3.0) if interval is None else interval
        solvers.append(Solver(client, mid, max_output_tokens=max_out, min_interval_s=gap))

    out = out_dir / run_id
    out.mkdir(parents=True, exist_ok=True)
    selector = Selector(options)
    rng = random.Random(seed)
    train_rows: list[dict[str, Any]] = []
    eval_rows: list[dict[str, Any]] = []
    aborted = ""
    with EvaluatorClient(benchmark, pool=pool) as evaluator:
        info = evaluator.info()
        if "error" in info:
            raise SystemExit(f"evaluator failed to start: {info['error']}")
        config = {"run_id": run_id, "kind": "learn", "models": [m for _, m in providers],
                  "options": [o.key for o in options], "cold": COLD, "per_task": per_task,
                  "split_seed": split_seed, "seed": seed, "pool": pool,
                  "train_tasks": [t.id for t in train], "eval_tasks": [t.id for t in ev_tasks],
                  "strategies": {k: {"version": s.version, "sha256": strategy_sha256(s)}
                                 for k, s in lib.items()},
                  "template_version": TEMPLATE_VERSION, "template_hashes": template_hashes(),
                  "benchmark": str(benchmark), "benchmark_sha256": info["benchmark_sha256"],
                  "evaluator_version": info["evaluator_version"],
                  "evaluator_code_sha256": info["evaluator_code_sha256"],
                  "isolation_level": ex.isolation_level(), "max_output_tokens": max_out,
                  "estimate_usd": round(est, 4), "fingerprint": fingerprint(),
                  "started": datetime.now(timezone.utc).isoformat()}
        (out / "config.json").write_text(json.dumps(config, indent=1) + "\n")

        def attempt(phase: str, opt: Option, task: Task) -> dict[str, Any]:
            s = lib[opt.strategy_id]
            slots = {"m1": solvers[opt.models[0]], "m2": solvers[opt.models[-1]]}
            ctx = CallContext(experiment_id=run_id, run_id=run_id, arm=f"{phase}:{opt.key}",
                              task_id=task.id)
            spent0 = ledger.committed_usd(task=(run_id, ctx.arm, task.id))
            t0 = time.monotonic()
            o = run_strategy(s, task, slots, sandbox_verifier(ex, task), ctx)
            verdict = evaluator.evaluate(task.id, o.code, pool)
            row = {"run_id": run_id, "phase": phase, "task_id": task.id,
                   "category": task.category, "difficulty": task.difficulty, "option": opt.key,
                   "strategy_id": s.id, "strategy_version": s.version,
                   "strategy_sha256": strategy_sha256(s),
                   "models": [solvers[i].model_id for i in opt.models],
                   "passed": bool(verdict.get("passed")),
                   "hidden": f"{verdict.get('n_passed', '?')}/{verdict.get('n_total', '?')}",
                   "failure": verdict.get("failure", ""), "visible_pass": o.visible_pass,
                   "model_calls": o.model_calls, "rounds_used": o.rounds_used,
                   "generated_tests": o.generated_tests, "generated_pass": o.generated_pass,
                   "shadow_usd": round(ledger.committed_usd(task=(run_id, ctx.arm, task.id))
                                       - spent0, 6),
                   "wall_s": round(time.monotonic() - t0, 2), "stopped": o.stopped,
                   "provider_errors": o.provider_errors,
                   "eval_error": str(verdict.get("error", ""))[:200], "trace": o.trace,
                   "code_sha256": hashlib.sha256(o.code.encode()).hexdigest(),
                   "evaluator_version": info["evaluator_version"],
                   "benchmark_sha256": info["benchmark_sha256"],
                   "template_version": TEMPLATE_VERSION,
                   "code": redact(o.code)}
            assert_no_secret(row)
            return row

        try:
            with (out / "train.jsonl").open("w") as f:
                order = list(train)
                rng.shuffle(order)
                for i, task in enumerate(order, 1):
                    tried: list[str] = []
                    for _ in range(per_task):
                        opt = selector.pick(task.category, rng, exclude=set(tried))
                        tried.append(opt.key)
                        row = attempt("train", opt, task)
                        if not row["eval_error"]:  # an infra failure is not evidence
                            selector.update(task.category, opt.key, row["passed"])
                            experience.write(ExperienceRow(pool="TRAIN", **{
                                k: row[k] for k in ExperienceRow.model_fields if k != "pool"}))
                        train_rows.append(row)
                        f.write(json.dumps(row) + "\n")
                        f.flush()
                        log(f"[train {i}/{len(order)}] {task.id:<16} {opt.key:<12} "
                            f"{'PASS' if row['passed'] else 'fail'} calls={row['model_calls']}")
            frozen = selector.frozen()
            with (out / "eval.jsonl").open("w") as f:
                for i, task in enumerate(ev_tasks, 1):
                    order_opts = list(options)
                    random.Random(f"{seed}:{task.id}").shuffle(order_opts)  # A11
                    for opt in order_opts:
                        row = attempt("eval", opt, task)
                        eval_rows.append(row)
                        f.write(json.dumps(row) + "\n")
                        f.flush()
                        log(f"[eval {i}/{len(ev_tasks)}] {task.id:<16} {opt.key:<12} "
                            f"{'PASS' if row['passed'] else 'fail'} calls={row['model_calls']}")
        except BudgetExceeded as e:
            aborted = f"{e.level} budget reached: {e}"
            frozen = selector.frozen()

    picks = {c: frozen.pick(c, rng).key for c in sorted({t.category for t in train + ev_tasks})}
    (out / "selector.json").write_text(json.dumps(
        {"picks": picks, "table": frozen.table(sorted(picks)),
         "stats": {f"{c}|{k}": v for (c, k), v in sorted(frozen.stats.items())}}, indent=1) + "\n")
    report = render_learn_report(config, train_rows, eval_rows, picks, frozen,
                                 _token_totals(telemetry, run_id), aborted)
    (out / "report.md").write_text(report)
    log(f"\nreport: {out / 'report.md'}")
    return {"run_id": run_id, "train_rows": train_rows, "eval_rows": eval_rows, "picks": picks,
            "report_path": out / "report.md", "aborted": aborted, "config": config}


def _hidden(rows: list[dict[str, Any]]) -> tuple[int, int]:
    p = t = 0
    for r in rows:
        a, _, b = str(r["hidden"]).partition("/")
        if a.isdigit() and b.isdigit():
            p, t = p + int(a), t + int(b)
    return p, t


def score_policies(eval_rows: list[dict[str, Any]], options: list[str], picks: dict[str, str]
                   ) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Policy -> its row per EVAL task, on tasks where every option finished."""
    by_task: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in eval_rows:
        by_task[r["task_id"]][r["option"]] = r
    done = sorted(t for t, rs in by_task.items() if all(o in rs for o in options))
    pol: dict[str, list[dict[str, Any]]] = {"warm": [], "cold": []}
    pol.update({o: [] for o in options})
    for t in done:
        rs = by_task[t]
        cat = next(iter(rs.values()))["category"]
        pol["warm"].append(rs[picks[cat]])
        pol["cold"].append(rs[COLD])
        for o in options:
            pol[o].append(rs[o])
    return pol, done


def render_learn_report(config: dict[str, Any], train_rows: list[dict[str, Any]],
                        eval_rows: list[dict[str, Any]], picks: dict[str, str], frozen: Selector,
                        tokens: dict[str, dict[str, int]], aborted: str) -> str:
    options = config["options"]
    pol, done = score_policies(eval_rows, options, picks)
    lines = [
        f"# Learning run {config['run_id']}", "",
        "> **Exploratory (M2).** Builder-written seed tasks, one run, small n. EVAL tasks were "
        "seen in M1, so this is not a held-out result and not evidence for H2 (D-018, D-027).",
        "", f"- Models: {', '.join(config['models'])}",
        f"- Options: {', '.join(options)} · cold = `{config['cold']}` · TRAIN options per task: "
        f"{config['per_task']}",
        f"- TRAIN {len(config['train_tasks'])} tasks · EVAL {len(config['eval_tasks'])} tasks "
        f"(split seed {config['split_seed']}) · benchmark sha256 "
        f"{config['benchmark_sha256'][:12]}… · evaluator {config['evaluator_version']}",
        f"- Sandbox {config['isolation_level']} · templates {config['template_version']} · "
        f"seed {config['seed']}",
        f"- EVAL compared on the **{len(done)} tasks** every option finished. Warm and cold are "
        "scored on the same runs (paired by task)."]
    if aborted:
        lines.append(f"- **Stopped early:** {aborted}")
    lines += ["", "## EVAL (frozen)", "",
              "| Policy | Solved | Pass rate | Hidden tests passed | Calls/task | Infra issues |",
              "|---|---|---|---|---|---|"]
    for name, rs in pol.items():
        n = len(rs)
        if not n:
            lines.append(f"| {name} | 0/0 | – | – | – | – |")
            continue
        solved = sum(r["passed"] for r in rs)
        hp, ht = _hidden(rs)
        infra = sum(bool(r["eval_error"]) + bool(r["stopped"]) + r["provider_errors"] for r in rs)
        label = {"warm": "**warm** (frozen selector)", "cold": f"**cold** ({COLD})"}.get(name, name)
        lines.append(f"| {label} | {solved}/{n} | {solved / n:.0%} | "
                     f"{hp}/{ht} ({hp / ht if ht else 0:.0%}) | "
                     f"{sum(r['model_calls'] for r in rs) / n:.1f} | {infra} |")
    if done:
        w = [r["passed"] for r in pol["warm"]]
        c = [r["passed"] for r in pol["cold"]]
        b = sum(x and not y for x, y in zip(w, c))
        cc = sum(y and not x for x, y in zip(w, c))
        lines += ["", f"**Warm vs cold:** {sum(w)}/{len(w)} vs {sum(c)}/{len(c)}; tasks only "
                      f"warm solved: {b}, only cold solved: {cc}; exact McNemar p = "
                      f"{mcnemar_p(b, cc):.2f}. One exploratory run: not significant evidence "
                      "either way at this n."]
        best = max(options, key=lambda o: sum(r["passed"] for r in pol[o]))
        lines += [f"Best single option on EVAL, chosen after the fact (optimistic): `{best}` "
                  f"{sum(r['passed'] for r in pol[best])}/{len(done)}."]
    lines += ["", "## What the selector learned (posterior mean pass rate per category)", "",
              "| Category | TRAIN runs | " + " | ".join(options) + " | Pick |",
              "|---" * (len(options) + 3) + "|"]
    for row in frozen.table(sorted(picks)):
        cells = [f"{row[o]:.2f}" for o in options]
        lines.append(f"| {row['category']} | {row['n']} | " + " | ".join(cells)
                     + f" | `{picks[row['category']]}` |")
    lines += ["", "## TRAIN stream", "",
              "| # | Task | Category | Option | Result | Calls |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(train_rows, 1):
        lines.append(f"| {i} | {r['task_id']} | {r['category']} | {r['option']} | "
                     f"{'✅' if r['passed'] else '❌'} {r['hidden']} | {r['model_calls']} |")
    if eval_rows:
        lines += ["", "## EVAL per task", "", "| Task | " + " | ".join(options) + " |",
                  "|---" * (len(options) + 1) + "|"]
        for t in sorted({r["task_id"] for r in eval_rows}):
            rs = {r["option"]: r for r in eval_rows if r["task_id"] == t}
            lines.append(f"| {t} | " + " | ".join(
                ("✅" if rs[o]["passed"] else "❌") + f" ({rs[o]['model_calls']})" if o in rs
                else "–" for o in options) + " |")
        lines += ["", "Cells: hidden-test verdict (model calls used)."]
    sel = [r for r in train_rows + eval_rows if r["strategy_id"] == "selftest"]
    if sel:
        lines += ["", f"Selftest: {sum(r['generated_tests'] for r in sel)} generated tests kept "
                      f"over {len(sel)} runs."]
    tk_in = sum(v.get("input", 0) for v in tokens.values())
    tk_out = sum(v.get("output", 0) for v in tokens.values())
    lines += ["", f"Tokens: {tk_in} input, {tk_out} output. Wall time in the jsonl files "
                  "includes free-tier pacing and retry waits."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--models", required=True, help="comma-separated provider:model specs")
    ap.add_argument("--strategies", help="comma-separated strategy ids (default: all)")
    ap.add_argument("--benchmark", default=str(ROOT / "benchmarks" / "seed"))
    ap.add_argument("--split-seed", type=int, default=1)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--per-task", type=int, default=1, help="options tried per TRAIN task")
    ap.add_argument("--pool", default="SEED")
    ap.add_argument("--max-output-tokens", type=int, default=8192)
    ap.add_argument("--interval", type=float)
    ap.add_argument("--limit-train", type=int)
    ap.add_argument("--limit-eval", type=int)
    ap.add_argument("--confirm-spend", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "reports" / "runs"))
    ap.add_argument("--state", default=str(ROOT / "state"))
    a = ap.parse_args(argv)
    try:
        r = run_learning(models=a.models.split(","),
                         strategies=a.strategies.split(",") if a.strategies else None,
                         benchmark=Path(a.benchmark), split_seed=a.split_seed, seed=a.seed,
                         per_task=a.per_task, confirm_spend=a.confirm_spend, pool=a.pool,
                         max_out=a.max_output_tokens, out_dir=Path(a.out),
                         state_dir=Path(a.state), interval=a.interval,
                         limit_train=a.limit_train, limit_eval=a.limit_eval)
    except Exception as e:  # noqa: BLE001
        print(redact(f"error: {type(e).__name__}: {e}"), file=sys.stderr)
        raise SystemExit(2) from None
    print(r["report_path"].read_text())


if __name__ == "__main__":
    main()
