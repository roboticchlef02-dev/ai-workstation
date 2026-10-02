# Next session — start here

**State (2026-10-02, end of session b):** M1 working loop built and running live on free Gemma 4 models. Branch `claude/vibrant-bardeen-b9y49d`.

## What exists (M1)
| Piece | Files |
|---|---|
| Secret guard | `src/aiws/secretguard.py` |
| Budget: shadow-cost prices, caps, reserve/settle ledger, preflight | `configs/{prices,budget}.yaml`, `src/aiws/{prices,budget}.py` |
| Providers: mock, record/replay, Gemini, OpenAI-compatible (OpenCode Zen, OpenRouter, Groq, local) | `src/aiws/providers/` |
| Metered call path + telemetry | `src/aiws/{metered,telemetry}.py` |
| **L3 sandbox executor** (setpriv + bwrap, per-run uid, rlimits, self-probe, fail closed) | `src/aiws/executor.py` |
| Benchmark format + harness + **seed benchmark** (27 tasks) | `src/aiws/{benchmark,harness}.py`, `benchmarks/seed/` |
| **Evaluator** (separate process, hidden tests, manifest check) | `src/aiws/evaluator.py` |
| **Arms A/C/D**, runner, report | `src/aiws/{arms,run}.py`, `reports/runs/` |

Run: see `README.md`. Sandbox tests need root + bwrap, so run pytest with an approved unsandboxed command, keys stripped:
`env -u GEMINI_API_KEY -u GROQ_API_KEY -u OPENROUTER_API_KEY -u OPENCODE_API_KEY python -m pytest -q`

## Ridha: open items
1. **Network access** (environment menu → Edit → Network access → allowed domains): add `api.groq.com` and `openrouter.ai` (keys already added). Optional: `opencode.ai` + `OPENCODE_API_KEY`. This unlocks cross-family models (Llama, DeepSeek, Qwen…).
2. Optional: branch protection for `main`.

## Prompt to paste into the next session
> Read CLAUDE.md, docs/NEXT_SESSION.md, docs/QUESTIONS.md and the end of docs/DECISIONS.md. Network access updated: yes/no. Continue.

## Builder checklist for the next session
1. Check CI on the latest push.
2. Read the latest report in `reports/runs/`. If Groq/OpenRouter are reachable, list their free models (no tokens), add price entries, and run a cross-family D.
3. **M1 gate** (`docs/gates/GATE-M1.md`) if not written yet: results, deviations, risks, fresh-context reviewer.
4. Then **M2** (learning: per-category strategy selection, warm vs cold) and **M3** (the Markdown armor pack, D-022/D-024), in that order.
5. Known gaps: no environment fingerprint in telemetry (R1); the ledger's running total lives in `state/` (not committed), so the global cap resets with each container; seed tasks lack a second independent solution and mutation check (D-025); evaluator shares the orchestrator's OS user (A10 → M4).
