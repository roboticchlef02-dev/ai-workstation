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
| OpenAI-compatible provider: OpenCode Zen, OpenRouter, Groq, local Ollama/llama.cpp/LM Studio (offline tests) | `src/aiws/providers/openai_compat.py`, `tests/test_openai_compat.py` |

## Ridha: open items
1. **Network access** (environment menu → Edit → Network access → allowed domains): add `api.groq.com` and `openrouter.ai` (keys already added), plus `opencode.ai` if you add an OpenCode key (`OPENCODE_API_KEY`, optional). Then start a new session.
2. **Q21:** knowledge as Markdown files (default yes).
3. Still open from before: branch protection for `main` (optional).

## Prompt to paste into the next session
> Read CLAUDE.md, docs/NEXT_SESSION.md, docs/QUESTIONS.md and the end of docs/DECISIONS.md. Q21 = …. Network access updated: yes/no. Continue M1. Stop when the conversation gets long, and update docs/NEXT_SESSION.md before stopping.

## Builder checklist for the next session
1. Check CI on the latest push.
2. Keys observed this session: Gemini, Groq, OpenRouter set, and hidden inside sandboxed commands. If an OpenCode key appears, verify the same (names only).
3. **List free models** (Groq, OpenRouter `:free`, Zen `/zen/v1/models`, Gemini; no tokens spent) with approved unsandboxed commands. Add the chosen free models to `configs/prices.yaml`.
4. **Confirm the Gemini model ID and prices** before any live call: list models (free, no tokens) with an approved unsandboxed command, then fix `configs/prices.yaml` (`verified`) and the provider default. Then one live smoke test only with Ridha's go-ahead: `pytest -m live --confirm-spend tests/test_gemini.py`.
5. **L3 executor**, security tests first (D-005, D-012, Gate 0 Phase 2 list):
   - refuses to run below L3 (fail closed)
   - `setpriv` to an unprivileged uid before bwrap; NPROC enforced (fork bomb contained)
   - no network; host FS hidden; no AF_UNIX path to host sockets; no setns escape
   - clean env (`secretguard.child_env`); timeout, memory, file-size limits
   - records the enforced `isolation_level`

   Nested bwrap hangs inside the dev sandbox (`--unshare-user`). Q14 = (b): run these tests via approved unsandboxed commands for now; pick (a) or (c) once the executor exists.
6. Then: evaluator process (stdin/stdout JSON, hidden tests), ~40-task seed benchmark, arms A/C/D, report.
7. Design to keep in mind: **portable knowledge** (D-022): general vs model-scoped memory, ~300-token cap, H4 transfer test (A13, proposed).
8. Not yet built: retry loop for `retryable` errors, environment fingerprint in telemetry (R1), run-level telemetry records.
