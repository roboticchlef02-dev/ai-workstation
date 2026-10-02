# Decisions log

Format: ID · date · context → choice · risk/consequence · status.
Status values: APPROVED (by Ridha), PROPOSED (awaiting Ridha), BUILDER (builder's call within plan; reversible).
Precedence: `CLAUDE.md` > Ridha-approved amendments > `PLAN.md` > handoffs. Conflicts → ask Ridha, never choose silently.

---

## Plan amendments from HANDOFF_FROM_CLAUDE.md

Per the handoff, these count as approved once Ridha hands over the file, which Ridha did on 2026-10-02. They modify `PLAN.md`, never `CLAUDE.md`'s safety rules. Each one goes into `PREREGISTRATION.md` when that file is written (before the first held-out run).

| ID | Amendment | Applies at | Status |
|---|---|---|---|
| A1 | 2×2 attribution on VALIDATION: {default, learned strategy} × {no memory, learned memory}. Explanatory only, not causal proof | Phase 8 | APPROVED |
| A2 | `docs/PROVIDER_STABILITY.md` + 15–20-task canary regression set re-run at start/end of each session. A drift flag is a validity risk, not a verdict | Gate 1 / every session | APPROVED |
| A3 | `docs/BENCHMARK_VALIDITY.md`: oracles, property-based tests, cross-family validation, mutation score per category, balance, flagged-not-dropped tasks, per-provider pass rates, canaries. A post-held-out flaw means benchmark v2, not a quiet fix | Gate 2 | APPROVED |
| A4 | Training-adequacy and learning-curve power analysis from PILOT; options with costs for Ridha | Gate 3 | APPROVED |
| A5 | Strategy ladder S1–S5 available as candidates from the start | Phase 5 | APPROVED |
| A6 | Preregistered best-of-N selection rule (N, ties, no-pass case), same for every sampling arm | Prereg | APPROVED |
| A7 | No post-hoc changes once held-out results are visible; later analyses labeled exploratory | Always | APPROVED |

---

## Phase 0 decisions

**D-001 · 2026-10-02 · ChatGPT's handoff was not received.**
The prompt says to read "ChatGPT's accompanying handoff". Only `CLAUDE.md`, `PLAN.md` and `HANDOFF_FROM_CLAUDE.md` were provided. → Proceeded with those three; nothing in Phase 0 depends on the missing file. Asked in Q6. · Risk: it may contain requirements not reflected here. · PROPOSED

**D-002 · 2026-10-02 · `.env` deny rules: explicit names, not wildcard + negation.**
First config used `Read(.env.*)` + `Read(!.env.example)`. The resolved OS sandbox config showed `.env.example` **denied**, and `cat .env.example` returned *Permission denied*: on Linux the glob expands to existing files, and the negation is not carved out at that layer. → Deny `.env`, `.env.local`, `.env.development`, `.env.production`, `.env.test`, `.env.secret` by name. `.gitignore` still ignores all `.env.*` except `.env.example`. Regression test added. · Risk: an unusual name (e.g. `.env.staging`) is git-ignored but not read-denied. Add names as needed. · BUILDER

**D-003 · 2026-10-02 · Provider keys are unset in Claude Code's sandboxed commands.**
→ `sandbox.credentials.envVars` denies all provider key names. Any live API call from the builder therefore needs an explicit, approved unsandboxed command, in addition to `--confirm-spend`. · Consequence: intended friction; mock/replay remains the default. · BUILDER

**D-004 · 2026-10-02 · Isolation detector must not infer isolation from an already-offline network.**
Running `detect_env.py` inside the dev sandbox reported `netns: BLOCKED` while the baseline was also blocked. That is a false positive. → Network isolation counts only when the same probe reaches the network without the namespace; otherwise the level stays lower. Regression test added. · BUILDER

**D-005 · 2026-10-02 · Process limits need a privilege drop.**
`RLIMIT_NPROC` is ignored for uid 0, including inside `bwrap --uid 65534`, because the outer uid is still root. → The Phase 2 executor must `setpriv` to an unprivileged uid before bwrap (shown to work), or use a pids cgroup. Implement and test in Phase 2, not now. · Risk if skipped: fork bombs are not contained. · BUILDER (spec for Phase 2)

**D-006 · 2026-10-02 · Isolation scale L0–L4 defined** (`docs/ENVIRONMENT.md`). Executor records the level it actually enforced, not the level the host could support. · BUILDER

**D-007 · 2026-10-02 · Repository layout.**
`src/aiws/` (package), `tests/`, `configs/` (`protected_paths.txt` is Control plane), `scripts/`, `docs/{gates,external_review,evaluator_tickets,handoffs}`, `benchmarks/` (`held_out/` git-ignored and never opened), `reports/`. `CLAUDE.md` and `PLAN.md` live at the root, where `CLAUDE.md` expects them. · BUILDER

**D-008 · 2026-10-02 · CI runs pytest on Python 3.11 and 3.12, with no secrets and no `live` tests.** No linter was added (CLAUDE.md keeps dependencies minimal). · BUILDER

**D-009 · 2026-10-02 · Research claims, status at Phase 0.** Nothing is cited in reports until it is re-checked.
- arXiv 2605.01566 (Wunderlich, Kaesberg, Wahle, Ruas, Gipp; ACL 2026 SRW): existence, venue and "debate +1.3 / mixture-of-agents +2.7 points over self-consistency at equal compute" **verified from the abstract**. The "self-refinement worse than CoT" claim is **not yet verified** (arxiv.org blocked here).
- arXiv 2601.09667 (MATTRL): exists. Experience-pool retrieval at test time confirmed from summaries. The "pools drift / stale heuristics" claim is **unverified**.
- Everything the handoff labels "reported by ChatGPT": **unverified**.

**D-010 · 2026-10-02 · Environment ≠ Ridha's PC.** PLAN Q1 asks about "the development machine". This session runs in a cloud container, which I measured. Ridha's PC is unknown. Asked as Q1 instead of assuming either. · PROPOSED

**D-011 · 2026-10-02 · Two dev-safety tests passed vacuously.**
CI (first run) failed `test_nothing_tracked_under_protected_paths`: the prefix check matched `.env.example` under `.env`. Locally it had passed only because nothing was tracked yet. → File entries now need an exact match, directory entries a prefix match. Both git-based tests now assert that the tracked-file list is non-empty. Lesson for later gates: a check over an empty set is not evidence. · BUILDER

---

## External review responses
(None yet. Gate 0 feedback will be classified ACCEPT / REJECT / DEFER here.)
