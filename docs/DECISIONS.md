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

**D-001 · 2026-10-02 · ChatGPT's handoff was not received at first.**
The prompt says to read "ChatGPT's accompanying handoff". Only `CLAUDE.md`, `PLAN.md` and `HANDOFF_FROM_CLAUDE.md` were provided. → Proceeded with those three; nothing in Phase 0 depends on the missing file. Asked in Q6. · **Resolved after Gate 0:** Ridha supplied it, stored as `docs/handoffs/HANDOFF_FROM_CHATGPT.md`. Read in full. Its three threats map to A1–A3 (already logged). Everything else in it repeats `CLAUDE.md`/`PLAN.md` (laws, gate protocol, reviewer instructions, spend rule). **No missed requirement found.**

**D-002 · 2026-10-02 · `.env` deny rules: explicit names, not wildcard + negation.**
First config used `Read(.env.*)` + `Read(!.env.example)`. The resolved OS sandbox config showed `.env.example` **denied**, and `cat .env.example` returned *Permission denied*: on Linux the glob expands to existing files, and the negation is not carved out at that layer. → Deny `.env`, `.env.local`, `.env.development`, `.env.production`, `.env.test`, `.env.secret` by name. `.gitignore` still ignores all `.env.*` except `.env.example`. Regression test added. · Risk: an unusual name (e.g. `.env.staging`, `.env.bak`, `.envrc`) or a nested `configs/.env.local` is git-ignored but not read-denied. · **Resolved by Q9 (2026-10-02):** template renamed to `env.example`; `Read/Edit(.env*)` denied at every depth. History: this narrows CLAUDE.md's "deny `.env*`" rule, and CLAUDE.md outranks everything, so it needs Ridha's decision (Q9) rather than a builder call.

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

**D-010 · 2026-10-02 · Environment ≠ Ridha's PC.** PLAN Q1 asks about "the development machine". This session runs in a cloud container, which I measured. Ridha's PC is unknown. Asked as Q1 instead of assuming either. · APPROVED (Q1: cloud environment)

**D-011 · 2026-10-02 · Two dev-safety tests passed vacuously.**
CI (first run) failed `test_nothing_tracked_under_protected_paths`: the prefix check matched `.env.example` under `.env`. Locally it had passed only because nothing was tracked yet. → File entries now need an exact match, directory entries a prefix match. Both git-based tests now assert that the tracked-file list is non-empty. Lesson for later gates: a check over an empty set is not evidence. · BUILDER

**D-012 · 2026-10-02 · Model-generated code runs only at L3+.** The reviewer showed that L1/L2 leave the host filesystem visible: hidden tests, DBs, `.env`, and Unix sockets that a network namespace doesn't block. That makes L1/L2 a leak path and a false-positive source. → The executor (Phase 2) disables execution below L3. This matches PLAN 6.4 ("if strong isolation cannot be provided, disable execution"). Before this, ENVIRONMENT.md wrongly allowed an L2 fallback. · BUILDER (clarifies plan; no architecture change)

**D-013 · 2026-10-02 · `.gitignore` covers non-directory forms.** `secrets`, `benchmarks/held_out*` (file, symlink, archive), `.envrc`, `id_rsa*`, `credentials.json`. The old `dir/` patterns missed a file or symlink with the same name. Test added. · BUILDER

**D-014 · 2026-10-02 · `live` tests skip unless `--confirm-spend`** (`tests/conftest.py`), even for a bare `pytest` run with keys present. Full spend accounting (estimate, per-run cap, running total, caps in a file the learning plane can't write) is Phase 1. · BUILDER

**D-015 · 2026-10-02 · Conflict: A2 canary set vs PLAN 5.1 "PILOT never reused".** A2 (approved) re-runs a 15–20-task PILOT subset every session. → A2 is a later, approved amendment, so it takes precedence for that subset only. Canary runs are tagged `pool=CANARY` and kept out of the experience log the learning engine reads. Flagged for Ridha's confirmation, no question needed unless Ridha objects. · **SUPERSEDED by proposed A11:** a separate CONTROL/SENTINEL set, so PILOT stays never-reused.

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

## External review — Gate 0 (ChatGPT)

Source: `docs/external_review/GATE-0-chatgpt.md`. Claude (chat) review: not received yet.
ChatGPT is a reviewer, not the decision-maker. ACCEPT means **the builder recommends it**. Items that change architecture, permissions or CLAUDE.md wording are binding only once Ridha confirms (Q11).

### Fact checks of the review's claims (2026-10-02)

| Claim | Result |
|---|---|
| Claude Haiku 4.5 at $1 / $5 per M tokens, active | **Verified** (Claude API skill, model table cached 2026-09-25). Alias `claude-haiku-4-5`; ChatGPT gave the dated snapshot `claude-haiku-4-5-20251001`. **Prefer the dated ID** (better for A2 immutability). Confirm via the Models API at Phase 1 |
| Newer Claude models restrict temperature/top_p | **Verified.** Sampling params return 400 on Opus 4.7+/Sonnet 5/Opus 5.5/Fable; Haiku 4.5 still accepts them. Supports A12 |
| Gemini 3.8 Flash $0.75 / $3.75 intro price until 2026-12-31 | **Reported by secondary sources** (pricing sites/news). Google's page wasn't fetched. Sources say the price **doubles on 2027-01-01**, which matters if runs cross the new year |
| MemSecBench (arXiv 2607.27080) on persistent memory poisoning | **Exists.** Abstract summary: 310 cases; malicious memory persists in 84.2% of cases; full write→execute chain 50.3%. The "laundering" work has no citation given → **unverified** |
| Claude Code permissions ≠ OS security boundary | Consistent with the docs I read in Phase 0 |

### Classification

| # | Point | Class | Reason / action |
|---|---|---|---|
| R1 | Run in the cloud env + environment fingerprint; abort if it changes | ACCEPT | Fingerprint (kernel, CPU/RAM quota, Python, SQLite, bwrap, package versions) recorded in telemetry from Phase 1. Abort-on-mismatch enforced at Phase 9 |
| R2 | Anthropic + Gemini; 50/50 generation; cross-family validation; by-generator analysis | ACCEPT | Matches my Q2 option (b). Pilot candidates Haiku 4.5 (dated ID) + Gemini 3.8 Flash, not presumed winners |
| R3 / A9 | Baseline too weak: best-of-N may use a fixed heterogeneous pool chosen on VALIDATION | ACCEPT, with modification | The core point is right: without it, a win could just mean "two model families beat one". **Modification:** keep B sampling-only (heterogeneous N, selected by visible tests, **no repair**). Let C's single model be chosen on VALIDATION from either family. Adding repair to B would turn B into C and the baseline into a small workstation. Tuning B/C on VALIDATION costs budget; counted in the Gate 3 estimate |
| R4 / A8 | Reword H1 to "adaptive workstation vs strongest simple non-learning baseline" | ACCEPT | Correct: H1 compares whole systems, so it can't isolate collaboration or verification. S1–S5 cover those as secondary questions |
| R5 / A10 | Evaluator: separate UID/sandbox, learning plane can't see key, files, environ, memory or results | ACCEPT, DEFER to Phase 2/4 | Same as the internal reviewer's #4. Designed and tested in Phase 2 (identities) and Phase 4 (evaluator) |
| R6 | Claude Code isn't the security boundary; enforce `allowUnsandboxedCommands=false`, `failIfUnavailable=true` now | ACCEPT principle; DEFER enforcement | Sequencing: `failIfUnavailable` before the setup script (Q8) would block fresh sessions from starting, and strict mode needs `excludedCommands` for `git commit`/`git push` (localhost signing/proxy). It is also a permission-settings change, so I won't make it on a reviewer's word; Ridha confirms in Q11. Order: Q8 → strict settings → verify |
| R7 | Budget hierarchy (global → experiment → task → call); env vars can only lower caps; persistent atomic ledger; reserve-then-settle for concurrency | ACCEPT, Phase 1 | The reserve-then-settle point is a real race the plan missed. Security tests are written first (CLAUDE.md) |
| R8 / A11 | Separate 15–20-task CONTROL/SENTINEL set; output hashes are telemetry only | ACCEPT | Supersedes D-015. Generated with the benchmark at Phase 3. Cost: ~20 extra tasks + 2 runs per session |
| R9 / A11 | Interleave arms per task in a preregistered random balanced order | ACCEPT | Plan gap, agreed. **Addition:** interleaving puts high-call arms (D/E) and low-call arms (A) under the same rate limits. Log 429s/retries per arm, and a rate-limit failure is a re-try, never a task failure |
| R10 / A12 | Sampling config per provider; record requested vs effective parameters | ACCEPT, Phase 1 | Verified above. "Fix temperatures in config" (PLAN 5.4) becomes "fix the sampling config each model supports" |
| R11 | Phase 6 adversarial memory tests (poisoning, laundering, false corroboration, tool echo, dormant triggers, Sybil, quarantine flooding) | ACCEPT, DEFER to Phase 6 | Fits the existing memory design; tests written before the memory code |
| Q1–Q5, Q7–Q10 | ChatGPT's recommended answers | AGREE (recommendation only) | They match my defaults, plus stronger conditions on Q7/Q8/Q10. **Still Ridha's call** → Q11 |
| Q6 | Resolved | ACCEPT | Handoff received; see D-001 |
| Phase 2 list | L3-only, fail closed, AF_UNIX and setns tests, per-run isolation, non-root executor, clean child env | ACCEPT | Union of internal reviewer #3/#8 and D-005/D-012. These become Phase 2's first tests |

No points rejected. One modification (A9) and one sequencing deferral (R6).

### New builder finding prompted by the review: the $150 ceiling probably doesn't cover the design

With the named candidates, a call (~2k in / 1k out) costs **~$0.007 on Haiku 4.5** and **~$0.005 on Gemini 3.8 Flash** (~$0.01 after the 2027 price change). My Gate 0 "cheap tier" assumed ~$0.003. ~29k calls → **~$170–230**, before A9 baseline tuning, the CONTROL set and repeats. Thinking/reasoning tokens would add more. **Low confidence** until the pilot. Gate 3 decides: raise the ceiling, or shrink pools/arms (e.g. HELD-OUT 300 → 200 lowers power; see A4). → Q3 updated.

### Amendments A8–A12 — approved by Ridha (Q11 yes, 2026-10-02)

| ID | Amendment | Applies at | Status |
|---|---|---|---|
| A8 | H1 := "The adaptive workstation improves verified task outcomes over the strongest simple non-learning baseline." No claim that H1 isolates collaboration or verification | Prereg | APPROVED (Q11) |
| A9 | B = fixed heterogeneous best-of-N (mixture, N, selection rule chosen on VALIDATION, frozen; no repair). C's model chosen on VALIDATION from either family. Strongest of A/B/C is the baseline | Phase 4 / prereg | APPROVED (Q11, 2026-10-02) — builder's modified version |
| A10 | Evaluator under a separate identity/sandbox; HELD-OUT returns the minimum permitted result; held-out results never enter the learning/memory pipeline | Phase 2/4 | APPROVED (Q11, 2026-10-02) |
| A11 | Per-task randomized balanced arm order (preregistered seed); CONTROL/SENTINEL set replaces PILOT reuse; drift signal = pass rate + provider metadata | Phase 3/9 | APPROVED (Q11, 2026-10-02) |
| A12 | Per-provider sampling config; log requested + effective parameters and response metadata | Phase 1 | APPROVED (Q11, 2026-10-02) |

---

## External review responses
(Claude (chat) Gate 0 review: pending.)

## After Gate 0 (Ridha: Q11 yes; free/subscription models; budget-tight)

**Gate 0 closed 2026-10-02.** Applied: Q9 (`env.example`, `.env*` denied everywhere), Q10 (sandbox `denyWrite` + `ask` on safety files, CODEOWNERS, more credential names unset), A8–A12 approved. Ridha's actions still open: setup script (Q8) and branch protection (see `docs/NEXT_SESSION.md`). Strict sandbox (`allowUnsandboxedCommands:false`, `failIfUnavailable:true`) waits until a fresh session shows the setup script works.

**D-016 · Cost unit = list-price dollars ("shadow cost"), whatever is actually billed.** Ridha may use free tiers or subscriptions, where billed cost ≈ $0. That would break dollar budget-matching (PLAN 5.3) and the spend caps. → Every call is charged its list price from the dated `configs/prices.yaml`; budget matching and caps use that number. Actual billed spend, tokens and calls are reported separately. · Keeps the comparison meaningful at $0 real spend. · PROPOSED (default, Q12)

**D-017 · Allowed access types.**
- (1) Paid API keys: yes.
- (2) Free-tier API keys (e.g. Gemini AI Studio): yes, with caveats:
  - ~10 requests/min and a few hundred/day, so long wall-clock runs
  - prompts may be used for training, which doesn't matter for synthetic tasks
  - record `billing_tier` on every call
- (3) Subscription chat apps (ChatGPT/Claude web): **no**. There is no official programmatic access, and terms risk.
- (4) Subscription agent CLIs (Claude Code `-p`, Codex, Gemini CLI): **not in v0.1**. They are agents with their own prompts and tools (a confound), they run commands on the host (a security issue), and their versions can't be pinned. Possible later as a separate provider type.

· PROPOSED (Q12)

**D-018 · Re-scope into small working milestones (budget-tight).** The 10-phase plan only produces a result at the end. → Proposed milestones, each ending in something that runs and a short gate:
- **M1 Working loop:** provider interface + mock/replay + 1–2 real providers (free tier OK), shadow-cost ledger, L3 sandbox executor (security tests first), evaluator process, ~40-task seed benchmark, arms A/C/D, auto report. ≈ PLAN phases 1, 2, 4 and a thin slice of 3 and 5.
- **M2 Learning:** experience log + per-category strategy selection (bandit), warm vs cold at small scale.
- **M3 Memory:** lessons with provenance/quarantine (PLAN phase 6).
- **M4 Real experiment:** full benchmark (300 held-out), prereg, A1/A9/A11, stats.

Laws, sandbox and secrets rules are unchanged from M1. **Validity rule:** M1–M3 results are labeled *exploratory* and never count as H1/H2 evidence. The true held-out set is generated fresh at M4 and never touched before. · Changes PLAN's phase order → PROPOSED (Q13)
