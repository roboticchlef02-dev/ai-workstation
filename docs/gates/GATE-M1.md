# GATE M1 — Working loop (2026-10-02)

## Status
M1 is built and has run live on free models. Results are **exploratory** (D-018): builder-written seed tasks, one run, no confidence intervals.

**Ridha decides:** close M1 and start M2 (learning) → M3 (Markdown armor pack)? Also: allow `api.groq.com` and `openrouter.ai` in Network access to get a second model family.

## 1. What was built
| Piece | Notes |
|---|---|
| Secret guard | Redaction of env-var values and known key formats; log formatter; persistence guard on every stored record; child processes get an allowlisted environment; git-history scan |
| Budget | Dated list prices (shadow cost, D-016); caps global > experiment > run > task > call, env may only lower; SQLite ledger with reserve-then-settle under `BEGIN IMMEDIATE` (race test: 240 attempts, exactly 100 granted); spend preflight |
| Providers | Interface, mock, record/replay (miss never falls through to live), Gemini, one OpenAI-compatible provider for OpenCode Zen / OpenRouter / Groq / local servers. Keys only in headers; errors classified billable/retryable |
| Metered call path | Secret check → output-token cap → price lookup (unknown model refused) → reservation → call → settle → telemetry (hashes, not texts) |
| L3 executor | `setpriv` to a per-run unprivileged uid, then bwrap (all namespaces, nested user namespaces disabled, only `/usr` read-only); rlimits for memory, processes, file size, open files, CPU; wall-clock timeout kills the group; output capped; self-probe before first use; anything below L3 disables execution |
| Benchmark + evaluator | Public task files vs hidden inputs + reference; hidden expected values computed in the sandbox; comparison outside the sandbox; separate evaluator process with key-free environment; manifest hash check; HELD_OUT/VALIDATION answers are pass/fail only |
| Seed benchmark | 27 tasks, 10 categories, difficulty 1–3 (D-025) |
| Arms + runner | A single shot · C execute + repair (≤ 4 calls) · D two models, pick passing, cross-model repair (≤ 4 calls); per-task random arm order (A11); retry on rate limits (R9); Markdown report |

## 2. Tests
- **193 tests** in total. Without root/bwrap (CI, dev sandbox) the sandbox tests skip visibly and the fail-closed tests run.
- Executor, evaluator and end-to-end tests **pass at L3** when run outside the dev sandbox (Q14 = b), keys stripped from the environment. Stable across 3 repeated runs.
- Mutation checks (D-011): removing the ledger's write lock → race test fails (105 granted > 100); removing `--disable-userns` → namespace-escape test fails.
- CI: green on every code push of M1.

## 3. Live run
_(filled in below when the run finishes)_

## 4. Deviations from the plan
- Milestones M1–M4 replace the phase order (Q13, D-018).
- Budget matching: max model calls per arm (A 1, C 4, D 4) rather than dollars, since free models have $0 list price (D-021, proposed).
- Arm B (best-of-N) not built yet; strategy DSL not built yet (D is code in M1).
- Seed tasks have no second independent solution, no mutation check, no human spot-check (D-025).
- Evaluator runs as the same OS user as the orchestrator (A10 → M4).

## 5. Open risks
1. **Same-family pair.** Only Google models are reachable today (Gemma 4 26B + 31B). D vs C mixes "two models" with "collaboration" (A9 caveat).
2. **Seed tasks written by the builder**, possibly easier or harder than intended; small n.
3. **Free-tier instability:** HTTP 500s and slow thinking calls (~60 s). Retries are logged; a retried call is not a task failure.
4. **Global spend cap resets per container:** the ledger lives in `state/` (not committed). Real spend is $0 on free models, so low impact now.
5. **Shared kernel:** bwrap is namespaces, not a VM (ENVIRONMENT.md).

## 6. Spend
Real: $0 (free models). Shadow (list price): see the run report.

## 7. Questions for reviewers
1. Is "max model calls" a fair budget match between C and D when D's calls go to two different models?
2. Does any path let code under test influence the evaluator's verdict beyond computing its own outputs?
3. Which measurement in M2 would best show that learning, not luck, improved D?

## 8. Fresh-context reviewer findings (verbatim summary, 2026-10-02)
Reviewer: a fresh-context subagent that had not seen the build conversation. Read-only; no network. Its report, condensed only for length (every finding kept):

1. **HIGH: D vs C comparison unfair.** (a) A and C only use model 1, while D also gets model 2: D can win through model access, not collaboration. (b) D keeps the best candidate, but C always takes the latest repair, even a worse one or empty code.
2. **MED-HIGH: forged result lines crash the run** (verified). The marker is readable from `sys.argv`. Payloads like `[1]`, `1`, `{"results":[1]}`, deep nesting, or a huge int in float mode raise uncaught exceptions in `run_cases`/`check`/`compare`. The runner exits without a report; the evaluator returns `{"error"}`, which is scored as a fail.
3. **MED: cleanup can be crashed by a deep directory tree** (verified). On a 3000-deep tree, `shutil.rmtree` raises RecursionError, which aborts the run and leaves the files on disk.
4. **MED: no total memory or disk limit.** The tmpfs `/tmp` has no size cap; `/work` is on the host disk; FSIZE is per file and AS per process (16 × 512 MB). A loop writing 16 MB files fills host RAM.
5. **MED: spend check can be bypassed** (verified). The estimate prices all D calls at model 2's rate, so a paid model 1 can slip through at $0. `billing_tier="free"` is hardcoded.
6. **MED (critical for M4): hidden data can reach the workstation.** The evaluator trusts the pool named in the request; failure strings carry the sandbox stderr tail, so `raise Exception(open('inputs.json').read())` leaks about 170 characters of hidden inputs; the orchestrator itself reads the hidden files to hash them.
7. **MED: the report hides infrastructure failures.** Evaluator errors, budget stops and post-retry provider failures all show as a plain fail. Retries count against the 20-calls-per-task ledger cap. Aborted runs give different denominators per arm. Wall time includes pacing and backoff.
8. **MED: the self-probe is weaker than the tests.** It doesn't check nested-userns blocking, a read-only `/usr`, capabilities or no-new-privs, or that the real limits apply. No seccomp filter. CI skips every L3 test.
9. **LOW-MED: the timeout test can't see surviving children.** `killpg` only reaches bwrap's group; the sandbox has its own session. Nothing asserts that the run's processes are gone.
10. **LOW-MED: `/tmp/aiws-exec` is a predictable path.** It is created with no owner or symlink check, so a local user could redirect root's writes and chowns.
11. **LOW: placeholder strings in model code abort runs** (verified). Strings like `API_KEY = "your-api-key-here"`, `Bearer …` or a PEM header raise SecretLeak inside repair prompts, and nothing catches it.
12. **LOW: errors are truncated before redaction** (verified). A key near character 284 of an error message keeps 16 of its characters.
13. **LOW: a malformed 200 response crashes the run.** JSONDecodeError and ValidationError are not ProviderErrors.
14. **LOW: evaluator validation gaps.** Empty `hidden_inputs` passes any code; the manifest sha256 is not recomputed; expected files are re-read per request without a hash check; `EVALUATOR_VERSION` is set by hand; NaN expected values are accepted.
15. **Methodology: seed tasks at ceiling.** Every completed live row so far passed in every arm, so there is no signal yet.

Found sound: expected values never enter the sandbox, and HELD_OUT responses are minimal; strict bool/int comparison through JSON; allowlisted environments, and the evaluator is key-free; keys only in headers, https enforced, no redirects; ledger locking, rounding, open reservations, unpriced refusal, env-only-lowers; sandbox flags (`--new-session`, `--cap-drop ALL`, `--disable-userns`, no-new-privs, per-run uid, root-only io files, `close_fds`); symlink-safe rmtree; replay miss never goes live.

Classification and actions: `docs/DECISIONS.md`, "M1 gate reviewer — classification".
