# GATE 0 — Foundation (2026-10-02)

## ⚡ Decisions Ridha must make (details in `docs/QUESTIONS.md`)

| # | Question | Recommended default |
|---|---|---|
| Q1 | Where will the experiment run? | **This cloud environment** (measured, isolation L3). Your PC is unmeasured |
| Q2 | Which two providers/models? Keys set? Spend limits? | Anthropic + Gemini or OpenAI, cheap-tier models. **No keys found yet. OpenAI/DeepSeek are blocked** by this environment's network policy |
| Q3 | Total budget / `MAX_RUN_COST_USD` | `$5` per run, **$150** total ceiling, revisited at Gate 3 with pilot data |
| Q4 | Spot-check 30 tasks? Time per gate? | Yes; ~1 h at Gate 2, 15–30 min otherwise |
| Q5 | Python-only tasks? | Yes |
| Q6 | ChatGPT's handoff wasn't included | Send it if it exists |
| Q7 | Where held-out tasks live (cloud wipes the disk; plaintext git is readable by every session) | Encrypted in git, key only in the evaluator's env |
| Q8 | Add a setup script (bubblewrap, socat, Python deps) | Yes. Exact lines are in `QUESTIONS.md` |

Note: the $100 Claude credit is **not** API credit. Provider API calls are billed separately.

## 1. What was created
- Skeleton: `src/aiws/`, `tests/`, `configs/`, `scripts/`, `docs/{gates,external_review,evaluator_tickets,handoffs}`, `benchmarks/` (`held_out/` git-ignored), `reports/`.
- `.gitignore` (secrets, held-out, DBs), `.env.example` (empty values), `pyproject.toml` (pydantic, httpx, pyyaml; pytest dev), GitHub Actions CI (pytest, Python 3.11 and 3.12, no secrets, `live` tests excluded).
- Dev safety: `.claude/settings.json` (deny rules, OS sandbox, provider keys unset in sandboxed commands, safety-config edits require approval), `configs/protected_paths.txt`.
- `scripts/detect_env.py`: host + isolation probe with a conservative L0–L4 scale.
- Tests: 22 checks (config consistency, git-ignore coverage, empty template, secret-pattern scan of tracked files, detector logic including 2 regression tests).
- Docs: `DECISIONS.md` (A1–A7 logged, D-001…D-010), `QUESTIONS.md`, `ENVIRONMENT.md`, this packet. `CLAUDE.md` and `PLAN.md` copied to the repo root.

**Tests actually run:** 22/22 passed locally through a stdlib stand-in for pytest, because pytest can't be installed from inside the dev sandbox (Q8). Real pytest runs in CI: see §5.

## 2. Detected environment (the cloud container, not Ridha's PC)
Ubuntu 24.04.4, x86_64 Firecracker VM, 4 vCPU, 15.7 GB RAM, Python 3.11.15, SQLite 3.45.1 with FTS5, running as root, no Docker daemon, ephemeral disk.

## 3. Achievable isolation: **L3** (shown by probes; not yet enforced by code)
bwrap with `--unshare-all --clearenv`: host filesystem hidden, network blocked (baseline reachable), env = `PATH` only. `RLIMIT_AS` enforced. Process-count limit enforced **only after dropping root** via `setpriv`.

## 4. Limits of that isolation
Shared kernel (namespaces, not a VM). The orchestrator runs as root, so the executor must drop privileges or fork bombs aren't contained (D-005). `/usr` is visible read-only. bwrap disappears on container restart without Q8. Wall-clock timing is noisy on a shared VM. Full list in `ENVIRONMENT.md`.

## 5. Development-security status
- ✅ Claude Code sandbox active in this session. Its resolved config lists `.env*` names, `secrets/` and `benchmarks/held_out/` as unreadable, and provider key env vars are unset.
- ✅ Bug found and fixed: `Read(.env.*)` + `!.env.example` made the template itself unreadable at the OS layer (D-002).
- ✅ Bug found and fixed: the detector reported network isolation when the network was already unreachable, a false positive (D-004).
- ⚠️ `failIfUnavailable` is still `false`: on a fresh container without bwrap, Claude Code silently runs unsandboxed. It turns on after Q8.
- ⚠️ Commits and pushes need a command outside the sandbox (the signing service and git proxy are on localhost). Each one was approved individually; the auto-mode classifier refused other bypasses (pip install, a protected-path probe).
- CI: run 1 failed (a real test bug, D-011, fixed). Run 2 pending.

## 6. Unresolved questions
Q1–Q8 above.

## 7. Deviations from the written plan
- PLAN Q1 ("which OS/RAM") reframed as "where will it run": the builder runs in a cloud container, not on Ridha's PC (D-010).
- ChatGPT's handoff not read; it was not provided (D-001).
- `.env` deny rules list names explicitly instead of a wildcard (D-002).
- Added `docs/ENVIRONMENT.md` and `scripts/detect_env.py`. Both are within Phase 0 scope ("detect OS and isolation capability"). No Phase 1+ code was written.

## 8. Estimated risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Held-out leakage through git history in an ephemeral cloud setup | High if plaintext | Invalidates H1/H2 | Q7 (encrypt) |
| Builder (Claude) is the same family as one solver and also builds the benchmark | Medium | Generator/solver bias | Generator ≠ solver provider; per-provider pass rates (A3); builder never prints held-out content |
| Budget estimate off by several times (no pilot yet) | High | Scope cuts later | Gate 3 re-estimate before any experiment spend |
| Silent sandbox fallback on a fresh container | Medium | Dev-safety gap | Q8 + `failIfUnavailable` |
| Shared-kernel escape by generated code | Low | Host compromise (VM-bounded) | L3 + privilege drop; VM boundary owned by the cloud provider |

## 9. Spend so far
**$0 API.** No provider was called. Reachability probes were unauthenticated and returned 401/403. Claude Code session usage isn't visible to me.

## 10. Three questions for external reviewers
1. Is **L3** (bwrap namespaces + rlimits + privilege drop, shared kernel, inside a cloud microVM) a sufficient boundary for running model-written solutions to programming puzzles in v0.1? Or should the plan require gVisor/VM-per-run, despite the cost and complexity?
2. For **held-out storage** in an ephemeral cloud repo: is "encrypted in git, key only in the evaluator's environment, unset in the builder's sandbox" adequate? Which leak paths remain (the builder invoking the evaluator, decrypted temp files, logs, the generator's own outputs at creation time)?
3. The **builder is a Claude model** that will also write the benchmark generator and see generator outputs. Is that a contamination or bias channel for H1 (e.g. tasks shaped toward Claude's strengths)? What concrete control should Gate 2 add beyond cross-family validation and per-provider pass rates?

## 11. Fresh-context reviewer findings (verbatim)
_Pending: the reviewer subagent is still running. Findings will be pasted here verbatim._
