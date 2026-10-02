# Next session — start here

**State (2026-10-02, end of session b):** Gate 0 closed. Q12 = yes, Q13 = yes → working in milestones (D-018). **M1 in progress.** Branch `claude/vibrant-bardeen-b9y49d`, CI green on every M1 code push (through `87cf0f0`).

## Verified this session
- Setup script works: bwrap 0.9.0, socat, setpriv, deps installed. `detect_env.py` outside the dev sandbox → **L3**.
- Keys (names only): `GEMINI_API_KEY` set, `ANTHROPIC_API_KEY` unset. The Gemini key is unset inside sandboxed commands (observed).
- 134 tests pass, 1 live test skipped (no `--confirm-spend`), even with the real key in the environment.

## M1 done so far (tests written first)
| Piece | Files |
|---|---|
| Secret guard: redaction, log formatter, persistence guard, clean child env, git-history scan | `src/aiws/secretguard.py`, `tests/test_secrets.py` |
| Shadow-cost price table (D-016), caps (env only lowers), reserve/settle SQLite ledger, spend preflight | `configs/prices.yaml`, `configs/budget.yaml`, `src/aiws/{prices,budget}.py`, `tests/test_budget.py` |
| Provider interface, mock, record/replay, metered call path, call telemetry | `src/aiws/providers/{base,mock,replay}.py`, `src/aiws/{metered,telemetry}.py`, `tests/test_providers.py` |
| Gemini provider (offline tests; live test gated) | `src/aiws/providers/gemini.py`, `tests/test_gemini.py` |

## Ridha: open items
1. **Q14** (strict sandbox: timing and form), in `docs/QUESTIONS.md`. Default: keep today's mode until the executor exists.
2. Optional: an `ANTHROPIC_API_KEY` for the second family (Q2/R2). Without it, M1 runs Gemini only.
3. Still open from before: branch protection for `main` (optional).

## Prompt to paste into the next session
> Read CLAUDE.md, docs/NEXT_SESSION.md, docs/QUESTIONS.md and the end of docs/DECISIONS.md. Q14 = …. Continue M1. Stop when the conversation gets long, and update docs/NEXT_SESSION.md before stopping.

## Builder checklist for the next session
1. Check CI on the latest push (docs-only since `87cf0f0`, which was green).
2. **Confirm the Gemini model ID and prices** before any live call: list models (free, no tokens) with an approved unsandboxed command, then fix `configs/prices.yaml` (`verified`) and the provider default. Then one live smoke test only with Ridha's go-ahead: `pytest -m live --confirm-spend tests/test_gemini.py`.
3. **L3 executor**, security tests first (D-005, D-012, Gate 0 Phase 2 list):
   - refuses to run below L3 (fail closed)
   - `setpriv` to an unprivileged uid before bwrap; NPROC enforced (fork bomb contained)
   - no network; host FS hidden; no AF_UNIX path to host sockets; no setns escape
   - clean env (`secretguard.child_env`); timeout, memory, file-size limits
   - records the enforced `isolation_level`

   Nested bwrap hangs inside the dev sandbox (`--unshare-user`), so these tests need the route Ridha picks in Q14.
4. Then: evaluator process (stdin/stdout JSON, hidden tests), ~40-task seed benchmark, arms A/C/D, report.
5. Not yet built: retry loop for `retryable` errors, environment fingerprint in telemetry (R1), run-level telemetry records.
