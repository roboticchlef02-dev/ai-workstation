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
First config used `Read(.env.*)` + `Read(!.env.example)`. The resolved OS sandbox config showed `.env.example` **denied**, and `cat .env.example` returned *Permission denied*: on Linux the glob expands to existing files, and the negation is not carved out at that layer. → Deny `.env`, `.env.local`, `.env.development`, `.env.production`, `.env.test`, `.env.secret` by name. `.gitignore` still ignores all `.env.*` except `.env.example`. Regression test added. · Risk: an unusual name (e.g. `.env.staging`, `.env.bak`, `.envrc`) or a nested `configs/.env.local` is git-ignored but not read-denied. · **Reclassified PROPOSED after the Gate 0 reviewer:** this narrows CLAUDE.md's "deny `.env*`" rule, and CLAUDE.md outranks everything, so it needs Ridha's decision (Q9) rather than a builder call.

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

**D-012 · 2026-10-02 · Model-generated code runs only at L3+.** The reviewer showed that L1/L2 leave the host filesystem visible: hidden tests, DBs, `.env`, and Unix sockets that a network namespace doesn't block. That makes L1/L2 a leak path and a false-positive source. → The executor (Phase 2) disables execution below L3. This matches PLAN 6.4 ("if strong isolation cannot be provided, disable execution"). Before this, ENVIRONMENT.md wrongly allowed an L2 fallback. · BUILDER (clarifies plan; no architecture change)

**D-013 · 2026-10-02 · `.gitignore` covers non-directory forms.** `secrets`, `benchmarks/held_out*` (file, symlink, archive), `.envrc`, `id_rsa*`, `credentials.json`. The old `dir/` patterns missed a file or symlink with the same name. Test added. · BUILDER

**D-014 · 2026-10-02 · `live` tests skip unless `--confirm-spend`** (`tests/conftest.py`), even for a bare `pytest` run with keys present. Full spend accounting (estimate, per-run cap, running total, caps in a file the learning plane can't write) is Phase 1. · BUILDER

**D-015 · 2026-10-02 · Conflict: A2 canary set vs PLAN 5.1 "PILOT never reused".** A2 (approved) re-runs a 15–20-task PILOT subset every session. → A2 is a later, approved amendment, so it takes precedence for that subset only. Canary runs are tagged `pool=CANARY` and kept out of the experience log the learning engine reads. Flagged for Ridha's confirmation, no question needed unless Ridha objects. · PROPOSED

---

## Gate 0 internal reviewer — classification

Fresh-context reviewer findings (verbatim in `docs/gates/GATE-0.md` §11).

| # | Finding | Class | Action |
|---|---|---|---|
| 1 | Dev sandbox can be bypassed (`allowUnsandboxedCommands` default, no `failIfUnavailable`) | ACCEPT (claim) / ASK (settings) | Claims downgraded in ENVIRONMENT.md and GATE-0. Strict mode is a permission change and also blocks commits/pushes → Q10 |
| 2 | Rule-defining files writable from Bash; CI runs on the builder's own push | ACCEPT / ASK | → Q10 (sandbox `denyWrite` + CODEOWNERS + branch protection need Ridha) |
| 3 | L1/L2 aren't isolation; Unix sockets; root `unshare --net` | ACCEPT | D-012: execution only at L3. setns and Unix-socket probes → Phase 2 security tests |
| 4 | Evaluator key readable by root/same-user processes (`/proc/<pid>/environ`) | ACCEPT, DEFER to Phase 2/Gate 2 | Q7 updated: separate users, non-root orchestrator, key file 0400, decryption only in a Ridha-launched Phase 9 session |
| 5 | `.gitignore` misses non-directory forms | ACCEPT | Fixed (D-013), test added |
| 6 | `.env*` rule narrowed without Ridha | ACCEPT | D-002 → PROPOSED, Q9 |
| 7 | "Keys unset" claim rests on an empty set; deny list name-based | ACCEPT | Claim marked "configured, not observed". Name-pattern check (names only) once keys exist → Phase 1 |
| 8 | Arms could mix isolation levels; NPROC shared across the uid | ACCEPT, DEFER to Phase 2/prereg | Preregister one level and abort on mismatch; per-run uid or pids cgroup |
| 9 | Spend-guard gaps | ACCEPT (part) / DEFER | conftest guard now (D-014); caps in a protected config + running total → Phase 1. Estimate inputs now shown in Q3 |
| 10 | Generator-family confound when only 2 families are reachable | ACCEPT | Added to Q2 (third family, or balanced generation + preregistered split) |
| 11 | Weak tests (secret regex, detector shape test, cwd-based fs probe, no raw L3 output) | ACCEPT (part) | fs probe fixed. Raw L3 output committed at Gate 1. Secret-regex broadening and history scan → Phase 1 (with real key formats in mind) |
| 12 | A2 canary set reuses PILOT | ACCEPT | D-015 |

---

## External review responses
(None yet. Gate 0 feedback will be classified ACCEPT / REJECT / DEFER here.)
