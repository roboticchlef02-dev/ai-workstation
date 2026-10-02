# Next session — start here

**State (2026-10-02, end of session b):** M1 working loop built, reviewed (fresh-context reviewer: 15 findings, 13 fixed, 2 partly deferred) and run live on free models. **Waiting at the M1 gate** for Ridha. Branch `claude/vibrant-bardeen-b9y49d`. All work committed and pushed.

## Results so far (details: `docs/gates/GATE-M1.md` §3, `reports/runs/`)
- Weak 7B (allam-2-7b): execute + repair raised hidden tests passed from 19% to 32%; full solves 2 to 3 of 27.
- Mid models (Qwen 3.8 27B, gpt-oss-20b): ceiling on 37 seed tasks; the one failure passes the visible examples, so repair can't see it.
- Two-model arm D: no gain over the best single model yet.

## What exists (M1)
| Piece | Files |
|---|---|
| Secret guard, budget (shadow cost, caps, reserve/settle ledger), fingerprint | `src/aiws/{secretguard,prices,budget,fingerprint}.py`, `configs/{prices,budget}.yaml` |
| Providers: mock, record/replay, Gemini, OpenAI-compatible (Groq, OpenRouter, OpenCode Zen, local) | `src/aiws/providers/` |
| Metered call path + telemetry | `src/aiws/{metered,telemetry}.py` |
| L3 sandbox executor (setpriv + bwrap, per-run uid, subreaper, sized tmpfs, self-probe, fail closed) | `src/aiws/executor.py` |
| Benchmark + harness + evaluator (separate process, fixed pool, failure categories) | `src/aiws/{benchmark,harness,evaluator}.py`, `benchmarks/seed/` (v0.2, 37 tasks) |
| Arms A1/C1/A2/C2/D, runner, report (`--rerender`) | `src/aiws/{arms,run}.py` |

Run: `README.md`. Sandbox tests need root + bwrap, so run them with an approved unsandboxed command and keys stripped:
`env -u GEMINI_API_KEY -u GROQ_API_KEY -u OPENROUTER_API_KEY -u OPENCODE_API_KEY python -m pytest -q` (224 pass).
Live run example (Groq is fast; Gemma via Gemini is ~60 s/call):
`PYTHONPATH=src python -m aiws.run --models groq:qwen/qwen3.8-27b,groq:openai/gpt-oss-20b --confirm-spend`

Keys present: GEMINI, GROQ, OPENROUTER (no OpenCode). Network: full access. OpenRouter free models: ~50 requests/day.

## Ridha decides (M1 gate)
1. Close M1 and start **M2** (learning which strategy and model work per task category, warm vs cold), then **M3** (Markdown armor pack, D-022/D-024)?
2. Optional: send `docs/gates/GATE-M1.md` to ChatGPT/Claude for an external review.

## Prompt to paste into the next session
> Read CLAUDE.md, docs/NEXT_SESSION.md, docs/gates/GATE-M1.md and the end of docs/DECISIONS.md. M1 gate: <close / changes>. Continue with M2. Stop when the conversation gets long, and update docs/NEXT_SESSION.md before stopping.

## Builder checklist for the next session
1. Check CI on the latest push.
2. If M1 is closed: M2. Candidate first strategy, from the results: **self-generated edge-case tests** (the model writes extra test inputs; only verified ones are used), since visible examples miss traps.
3. Harder or more varied tasks are still needed for mid models. Weak models (allam-2-7b, small OpenRouter `:free` models) show effects on the current set.
4. Deferred from the reviewer: cgroup memory/pids caps and a seccomp filter (before running on Ridha's PC); billing tier per provider (only if a paid key ever appears); preregistered infra-failure rules (M4).
5. Known gaps: the ledger total lives in `state/` (not committed); seed tasks lack a second solution and mutation check (D-025/D-026); evaluator shares the orchestrator's OS user (A10 → M4).
