# Next session — start here

**State (2026-10-02, end of session c):** M1 gate closed by Ridha. **M2 (learning) built and tested; first live learning run: see below.** Branch `claude/eloquent-goldberg-17kjla` (fast-forwarded from the M1 branch `claude/vibrant-bardeen-b9y49d`, then M2 on top). All work committed and pushed. CI green on this branch.

## Results of this session
- Live learning run `20261002T183158Z-learn-s1` (allam-2-7b) **in progress** at the time of this commit (18 of 42 TRAIN attempts). Results follow when it finishes.

## What M2 added (D-027, D-028)
| Piece | Files |
|---|---|
| Strategy DSL v0: YAML data, fixed operators (`CALL_MODEL`, `PARALLEL`, `VERIFY`, `REPAIR`, `FINALIZE`), model slots only, template IDs only, call cap from budget.yaml | `src/aiws/strategy.py`, `strategies/*.yaml`, `tests/test_strategy.py` (55 tests, written first) |
| Template library (versioned, hashed into every run config) | `src/aiws/templates.py` |
| Interpreter (fixed selection rule; generated tests untrusted, filtered, sandbox only) | `src/aiws/interpreter.py`, `tests/test_interpreter.py` |
| M1 arms A/C/D now run as strategy files `single`/`repair`/`duo` (M1 e2e test unchanged and passing) | `src/aiws/arms.py` |
| New strategy `selftest`: the model writes edge-case tests from the statement; visible examples stay the hard gate | `strategies/selftest.yaml` |
| Experience log (TRAIN rows only; frozen refuses writes; secret guard) | `src/aiws/experience.py` |
| Per-category Thompson selector with pooled prior (κ = 2); frozen = greedy, no updates | `src/aiws/selector.py`, `tests/test_learning.py` |
| Learning runner: TRAIN stream → freeze → EVAL (every option on every task; warm/cold scored paired) + report with McNemar | `src/aiws/learn.py`, `tests/test_learn.py` |

Tests: 313 (312 pass at L3; the one failure is Q22, full-clone history scan only). Run them unsandboxed with keys stripped:
`env -u GEMINI_API_KEY -u GROQ_API_KEY -u OPENROUTER_API_KEY -u OPENCODE_API_KEY python -m pytest -q`

Live learning run (Groq free tier: allam-2-7b is limited to 6,000 tokens/min, so keep output at 1,024 and pace 15 s):
`PYTHONPATH=src python -m aiws.learn --models groq:allam-2-7b --strategies single,repair,selftest --per-task 2 --max-output-tokens 1024 --interval 15 --confirm-spend`

## Ridha decides
1. **Q22:** CI history scan flags a placeholder in pushed history. Recommended (a): exempt that one value by hash. (The auto-mode check blocked me from doing it without you.)
2. M2 gate: after the next session's second run and the fresh-context reviewer.

## Prompt to paste into the next session
> Read CLAUDE.md, docs/NEXT_SESSION.md and the end of docs/DECISIONS.md. Q22: <a / b / c>. Continue M2 and prepare the M2 gate. Stop when the conversation gets long, and update docs/NEXT_SESSION.md before stopping.

## Builder checklist for the next session
1. Check CI on the latest push.
2. A second live run for variance: same settings, `--seed 2` (and `--split-seed 2` for a different split). If time allows, a second model family on OpenRouter `:free` (≈ 50 requests/day: too few for a full run; use `--limit-train`/`--limit-eval`).
3. M2 gate packet `docs/gates/GATE-M2.md` with a fresh-context reviewer (PLAN 9). Questions for the reviewer: can a strategy file widen anything; can EVAL outcomes reach the selector; is offline scoring of warm/cold on shared runs fair.
4. Then M3 (Markdown armor pack: lessons with provenance, D-022/D-024).
5. Still deferred: cgroup memory/pids caps and seccomp (before Ridha's PC); separate evaluator identity (A10, M4); seed tasks lack a second solution and mutation check (D-025/D-026).
