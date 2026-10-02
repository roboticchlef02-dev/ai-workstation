"""M1 experiment runner: tasks x arms -> evaluator verdicts -> results + Markdown report.

  python -m aiws.run --models gemini:gemini-2.5-flash --arms A,C,D --limit 5 --confirm-spend

Model specs: gemini:<model>, groq:<model>, openrouter:<model>, opencode:<model>,
local:<model>[@http://127.0.0.1:11434/v1], mock:<model> (tests). The first model is the
Arms: A<i> single shot and C<i> execute + repair on model i; D uses models 1 and 2 (or model 1
twice). Default: every arm for the given models, so D is compared with the best single model.

Safety: any non-zero estimate needs --confirm-spend (CLAUDE.md); execution needs L3; every
call goes through the metered client (secrets check, budget, telemetry).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiws import arms as arms_mod
from aiws.arms import Solver, run_arm
from aiws.benchmark import Task, load_tasks
from aiws.budget import BudgetExceeded, Ledger, load_caps, spend_preflight
from aiws.evaluator import EvaluatorClient
from aiws.executor import SandboxExecutor
from aiws.fingerprint import fingerprint
from aiws.metered import CallContext, MeteredClient
from aiws.prices import PriceTable
from aiws.providers.base import GenerateRequest, Message, ModelProvider
from aiws.secretguard import assert_no_secret, redact
from aiws.telemetry import Telemetry

ROOT = Path(__file__).resolve().parents[2]
ARM_MAX_CALLS = {"A": lambda r: 1, "C": lambda r: 1 + r, "D": lambda r: 2 + r}  # by letter
# Free-tier pacing defaults (seconds between calls), per provider.
DEFAULT_INTERVAL = {"gemini": 6.0, "groq": 2.5, "openrouter": 4.0, "opencode": 3.0,
                    "local": 0.0, "mock": 0.0}


def make_provider(spec: str) -> tuple[ModelProvider, str]:
    """Returns (provider, namespaced model_id)."""
    kind, _, model = spec.partition(":")
    if not model:
        raise ValueError(f"model spec must be provider:model, got {spec!r}")
    if kind == "mock":
        from aiws.providers.mock import MockProvider
        return MockProvider(model_id=model), model
    if kind == "gemini":
        from aiws.providers.gemini import GeminiProvider
        mid = f"gemini/{model}"
        return GeminiProvider(model_id=mid, api_model=model, billing_tier="free"), mid
    from aiws.providers.openai_compat import OpenAICompatProvider
    remote = {"groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
              "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
              "opencode": ("https://opencode.ai/zen/v1", "OPENCODE_API_KEY")}
    if kind in remote:
        base, key = remote[kind]
        mid = f"{kind}/{model}"
        return OpenAICompatProvider(name=kind, base_url=base, model_id=mid, api_model=model,
                                    key_env=key, billing_tier="free"), mid
    if kind == "local":
        name, _, url = model.partition("@")
        mid = f"local/{name}"
        return OpenAICompatProvider(name="local", base_url=url or "http://127.0.0.1:11434/v1",
                                    model_id=mid, api_model=name, key_env=None,
                                    billing_tier="none"), mid
    raise ValueError(f"unknown provider {kind!r}")


def arm_parts(spec: str) -> tuple[str, int]:
    """'A1' -> ('A', 0), 'C2' -> ('C', 1), 'D' -> ('D', 0); 'A'/'C' mean model 1."""
    letter, num = spec[:1], spec[1:]
    if letter not in ARM_MAX_CALLS or (num and not num.isdigit()) or (letter == "D" and num):
        raise ValueError(f"unknown arm {spec!r} (use A1, C1, A2, C2, D)")
    return letter, (int(num) - 1 if num else 0)


def default_arms(n_models: int) -> list[str]:
    return ["A1", "C1", "A2", "C2", "D"] if n_models >= 2 else ["A1", "C1", "D"]


def arm_models(spec: str, n_models: int) -> list[int]:
    letter, idx = arm_parts(spec)
    if letter == "D":
        return [0, 1] if n_models >= 2 else [0]
    if idx >= n_models:
        raise ValueError(f"arm {spec} needs model {idx + 1}, only {n_models} given")
    return [idx]


def estimate_usd(tasks: list[Task], arm_list: list[str], providers: list[tuple[ModelProvider, str]],
                 prices: PriceTable, rounds: dict[str, int], max_out: int) -> float:
    """Worst case: every arm uses all its calls, each call uses the full output allowance and
    is priced at the dearest model the arm may call (reviewer #5)."""
    today = datetime.now(timezone.utc).date()
    total = 0.0
    for t in tasks:
        prompt = arms_mod.SOLVE.format(statement=t.statement, signature=t.signature,
                                       examples=arms_mod.examples_text(t)) * 2  # repair ~2x
        for spec in arm_list:
            letter, _ = arm_parts(spec)
            per_call = 0.0
            for i in arm_models(spec, len(providers)):
                prov, mid = providers[i]
                req = GenerateRequest(model_id=mid, system=arms_mod.SYSTEM, max_output_tokens=max_out,
                                      messages=(Message(role="user", content=prompt),))
                per_call = max(per_call, prov.estimate_cost_usd(req, prices, on=today))
            total += ARM_MAX_CALLS[letter](rounds[letter]) * per_call
    return total


def run_experiment(*, models: list[str], arm_list: list[str] | None, benchmark: Path,
                   limit: int | None, task_ids: list[str] | None, seed: int, confirm_spend: bool,
                   pool: str, rounds: dict[str, int], max_out: int, out_dir: Path,
                   state_dir: Path, interval: float | None = None,
                   providers: list[tuple[ModelProvider, str]] | None = None,
                   log=print) -> dict[str, Any]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-s{seed}"
    caps = load_caps()
    prices = PriceTable.load()
    state_dir.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(state_dir / "ledger.sqlite", caps)
    telemetry = Telemetry(state_dir / "telemetry.sqlite")
    tasks = load_tasks(benchmark)  # public task files only; hidden files stay with the evaluator
    if task_ids:
        tasks = [t for t in tasks if t.id in set(task_ids)]
    if limit:
        tasks = tasks[:limit]
    providers = providers or [make_provider(m) for m in models]
    arm_list = arm_list or default_arms(len(providers))
    for spec in arm_list:
        arm_models(spec, len(providers))  # validate early

    est = estimate_usd(tasks, arm_list, providers, prices, rounds, max_out)
    log(spend_preflight(est, confirm_spend=confirm_spend, caps=caps, ledger=ledger))
    ex = SandboxExecutor()
    if ex.isolation_level() != "L3":
        raise SystemExit(f"refusing to run: sandbox is {ex.isolation_level()} ({ex.why_not_l3()})")

    solvers = []
    for prov, mid in providers:
        client = MeteredClient(prov, ledger=ledger, prices=prices, telemetry=telemetry)
        gap = DEFAULT_INTERVAL.get(prov.name, 3.0) if interval is None else interval
        solvers.append(Solver(client, mid, max_output_tokens=max_out, min_interval_s=gap))

    out_dir = out_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    aborted = ""
    with EvaluatorClient(benchmark, pool=pool) as ev:
        info = ev.info()  # the benchmark hash comes from the evaluator, not from hidden files
        if "error" in info:
            raise SystemExit(f"evaluator failed to start: {info['error']}")
        config = {"run_id": run_id, "models": [mid for _, mid in providers], "arms": arm_list,
                  "rounds": rounds, "seed": seed, "pool": pool, "max_output_tokens": max_out,
                  "benchmark": str(benchmark.relative_to(ROOT)) if benchmark.is_relative_to(ROOT)
                  else str(benchmark), "benchmark_sha256": info["benchmark_sha256"],
                  "evaluator_version": info["evaluator_version"],
                  "evaluator_code_sha256": info["evaluator_code_sha256"],
                  "template_version": arms_mod.TEMPLATE_VERSION,
                  "isolation_level": ex.isolation_level(), "estimate_usd": round(est, 4),
                  "fingerprint": fingerprint(),
                  "started": datetime.now(timezone.utc).isoformat(), "n_tasks": len(tasks)}
        (out_dir / "config.json").write_text(json.dumps(config, indent=1) + "\n")
        with (out_dir / "results.jsonl").open("w") as fout:
            for i, task in enumerate(tasks, 1):
                order = list(arm_list)
                random.Random(f"{seed}:{task.id}").shuffle(order)  # A11: random arm order per task
                for spec in order:
                    letter, _ = arm_parts(spec)
                    ctx = CallContext(experiment_id=run_id, run_id=run_id, arm=spec, task_id=task.id)
                    spent0 = ledger.committed_usd(task=(run_id, spec, task.id))
                    t0 = time.monotonic()
                    arm_solvers = [solvers[j] for j in arm_models(spec, len(solvers))]
                    try:
                        o = run_arm(letter, task, arm_solvers, ex, ctx, rounds=rounds.get(letter, 0))
                    except BudgetExceeded as e:
                        aborted = f"{e.level} budget reached: {e}"
                        break
                    verdict = ev.evaluate(task.id, o.code, pool)
                    row = {"run_id": run_id, "task_id": task.id, "category": task.category,
                           "difficulty": task.difficulty, "arm": spec,
                           "passed": bool(verdict.get("passed")),
                           "hidden": f"{verdict.get('n_passed', '?')}/{verdict.get('n_total', '?')}",
                           "failure": verdict.get("failure", ""),
                           "visible_pass": o.visible_pass, "model_calls": o.model_calls,
                           "rounds_used": o.rounds_used, "winner_model": o.winner_model,
                           "shadow_usd": round(ledger.committed_usd(task=(run_id, spec, task.id))
                                               - spent0, 6),
                           "wall_s": round(time.monotonic() - t0, 2), "stopped": o.stopped,
                           "provider_errors": o.provider_errors,
                           "eval_error": str(verdict.get("error", ""))[:200], "trace": o.trace,
                           "code": redact(o.code)}
                    assert_no_secret(row)
                    rows.append(row)
                    fout.write(json.dumps(row) + "\n")
                    fout.flush()
                    log(f"[{i}/{len(tasks)}] {task.id:<16} arm {spec}: "
                        f"{'PASS' if row['passed'] else 'fail'}  calls={o.model_calls} "
                        f"visible={'ok' if o.visible_pass else 'no'}")
                if aborted:
                    break
    errors = [e for s in solvers for e in s.errors]
    tokens = _token_totals(telemetry, run_id)
    report = render_report(config, rows, tokens, aborted, errors)
    (out_dir / "report.md").write_text(report)
    log(f"\nreport: {out_dir / 'report.md'}")
    return {"run_id": run_id, "rows": rows, "report_path": out_dir / "report.md",
            "aborted": aborted, "config": config}


def _token_totals(telemetry: Telemetry, run_id: str) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for rec in telemetry.calls():
        if rec.get("run_id") != run_id:
            continue
        a = out[rec["arm"]]
        a["input"] += rec.get("input_tokens") or 0
        a["output"] += rec.get("output_tokens") or 0
        a["errors"] += 0 if rec.get("ok") else 1
    return out


def _hidden_totals(rows: list[dict[str, Any]]) -> tuple[int, int]:
    passed = total = 0
    for r in rows:
        a, _, b = str(r.get("hidden", "")).partition("/")
        if a.isdigit() and b.isdigit():
            passed, total = passed + int(a), total + int(b)
    return passed, total


def rerender(run_dir: Path, state_dir: Path) -> Path:
    """Rebuild report.md from a run's saved config and results (e.g. after a report change)."""
    config = json.loads((run_dir / "config.json").read_text())
    rows = [json.loads(x) for x in (run_dir / "results.jsonl").read_text().splitlines() if x]
    tokens = _token_totals(Telemetry(state_dir / "telemetry.sqlite"), config["run_id"]) \
        if (state_dir / "telemetry.sqlite").exists() else {}
    done = len({r["task_id"] for r in rows})
    aborted = "" if done == config["n_tasks"] else f"only {done} of {config['n_tasks']} tasks ran"
    (run_dir / "report.md").write_text(render_report(config, rows, tokens, aborted, []))
    return run_dir / "report.md"


def arm_label(spec: str, models: list[str]) -> str:
    letter, idx = arm_parts(spec)
    short = [m.split("/")[-1] for m in models]
    if letter == "D":
        return f"{spec} two-model workstation ({' + '.join(short[:2])})"
    kind = "single shot" if letter == "A" else "execute + repair"
    return f"{spec} {kind} ({short[idx] if idx < len(short) else '?'})"


def render_report(config: dict[str, Any], rows: list[dict[str, Any]],
                  tokens: dict[str, dict[str, int]], aborted: str, errors: list[str]) -> str:
    arms = config["arms"]
    models = config["models"]
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)
    # Compare only tasks that every arm finished (reviewer #7: equal denominators).
    done = {tid for tid in {r["task_id"] for r in rows}
            if all(any(r["task_id"] == tid for r in by_arm[a]) for a in arms)}
    lines = [
        f"# Run {config['run_id']}",
        "",
        "> **Exploratory (M1).** Builder-written seed tasks, one run, no confidence intervals. "
        "This shows the loop works; it is not evidence for H1/H2 (D-018).",
        "",
        f"- Models: {', '.join(models)}",
        f"- Tasks: {config['n_tasks']} from `{config['benchmark']}` "
        f"(sha256 {config['benchmark_sha256'][:12]}…), pool {config['pool']}",
        f"- Arms: {', '.join(arms)} · repair rounds {config['rounds']} · max output tokens "
        f"{config['max_output_tokens']}",
        f"- Sandbox {config['isolation_level']} · evaluator {config['evaluator_version']} · "
        f"templates {config['template_version']} · seed {config['seed']}",
        f"- Compared on the **{len(done)} tasks** that every arm finished.",
    ]
    if aborted:
        lines.append(f"- **Stopped early:** {aborted}")
    lines += ["", "## Results", "",
              "| Arm | Solved | Pass rate | Hidden tests passed | Model calls | Calls/task | "
              "Input tok | Output tok | Shadow $ | Infra issues* |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    rates = {}
    for arm in arms:
        rs = [r for r in by_arm.get(arm, []) if r["task_id"] in done]
        n = len(rs)
        solved = sum(r["passed"] for r in rs)
        rates[arm] = solved / n if n else 0.0
        calls = sum(r["model_calls"] for r in rs)
        infra = sum(bool(r["eval_error"]) + bool(r["stopped"]) + r.get("provider_errors", 0)
                    for r in rs)
        tk = tokens.get(arm, {})
        hp, ht = _hidden_totals(rs)
        lines.append(
            f"| {arm_label(arm, models)} | {solved}/{n} | {solved / n:.0%} | "
            f"{hp}/{ht} ({hp / ht:.0%}) | {calls} | "
            f"{calls / n:.1f} | {tk.get('input', 0)} | {tk.get('output', 0)} | "
            f"{sum(r['shadow_usd'] for r in rs):.4f} | {infra} |"
            if n and ht else f"| {arm_label(arm, models)} | 0/0 | – | – | 0 | – | 0 | 0 | 0 | 0 |")
    lines += ["", "Hidden tests passed: partial credit, summed over tasks (a task counts as solved "
              "only if all its hidden tests pass)."]
    lines += ["", "\\* Infra issues: provider calls that failed after retries, budget stops and "
              "evaluator errors. Each one also counts as a fail in this table.",
              "Model calls exclude retried rate-limit errors. Wall time (in results.jsonl) "
              "includes free-tier pacing and retry waits."]
    singles = [a for a in arms if arm_parts(a)[0] in "AC"]
    if "D" in arms and singles and done:
        best = max(singles, key=lambda a: rates[a])
        diff = rates["D"] - rates[best]
        lines += ["", f"**D vs the best single-model arm ({best}):** "
                      f"{rates['D']:.0%} vs {rates[best]:.0%} ({diff:+.0%}). "
                      "One exploratory run: not a significant result either way."]
    cats = sorted({r["category"] for r in rows if r["task_id"] in done})
    if cats:
        lines += ["", "## By category (solved / tasks)", "",
                  "| Category | " + " | ".join(arms) + " |", "|---" * (len(arms) + 1) + "|"]
        for c in cats:
            cells = []
            for arm in arms:
                rs = [r for r in by_arm.get(arm, []) if r["category"] == c and r["task_id"] in done]
                cells.append(f"{sum(r['passed'] for r in rs)}/{len(rs)}")
            lines.append(f"| {c} | " + " | ".join(cells) + " |")
        lines += ["", "## Per task", "", "| Task | Difficulty | " + " | ".join(arms) + " |",
                  "|---" * (len(arms) + 2) + "|"]
        for tid in sorted({r["task_id"] for r in rows}):
            rs = {r["arm"]: r for r in rows if r["task_id"] == tid}
            diff = next(iter(rs.values()))["difficulty"]
            cells = [("✅" if rs[a]["passed"] else "❌") + f" ({rs[a]['model_calls']})"
                     if a in rs else "–" for a in arms]
            lines.append(f"| {tid} | {diff} | " + " | ".join(cells) + " |")
        lines += ["", "Cells: hidden-test verdict (model calls used)."]
    if errors:
        lines += ["", f"## Provider errors ({len(errors)})", ""]
        lines += [f"- {e}" for e in errors[:10]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--models", help="comma-separated provider:model specs")
    ap.add_argument("--rerender", help="rebuild report.md for this run directory and exit")
    ap.add_argument("--arms", help="e.g. A1,C1,A2,C2,D (default: all arms for the given models)")
    ap.add_argument("--benchmark", default=str(ROOT / "benchmarks" / "seed"))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--tasks", help="comma-separated task ids")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--pool", default="SEED")
    ap.add_argument("--rounds-c", type=int, default=3)
    ap.add_argument("--rounds-d", type=int, default=2)
    ap.add_argument("--max-output-tokens", type=int, default=8192)
    ap.add_argument("--interval", type=float, help="seconds between calls (default: per provider)")
    ap.add_argument("--confirm-spend", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "reports" / "runs"))
    ap.add_argument("--state", default=str(ROOT / "state"))
    a = ap.parse_args(argv)
    if a.rerender:
        print(rerender(Path(a.rerender), Path(a.state)).read_text())
        return
    if not a.models:
        ap.error("--models is required")
    try:
        r = run_experiment(
            models=a.models.split(","), arm_list=a.arms.split(",") if a.arms else None,
            benchmark=Path(a.benchmark),
            limit=a.limit, task_ids=a.tasks.split(",") if a.tasks else None, seed=a.seed,
            confirm_spend=a.confirm_spend, pool=a.pool,
            rounds={"A": 0, "C": a.rounds_c, "D": a.rounds_d}, max_out=a.max_output_tokens,
            out_dir=Path(a.out), state_dir=Path(a.state), interval=a.interval)
    except Exception as e:  # noqa: BLE001
        print(redact(f"error: {type(e).__name__}: {e}"), file=sys.stderr)
        raise SystemExit(2) from None
    print(r["report_path"].read_text())


if __name__ == "__main__":
    main()
