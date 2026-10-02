# AI Workstation v0.1 — Build Plan and Experimental Design

Prepared by Claude and ChatGPT (reviewing each other's drafts) for Ridha, 2026-10-02.
Builder: Claude Code. Read `CLAUDE.md` first; it holds the standing rules.

---

## 0. How to use this document

- This is a plan, not scripture. If you find a flaw, record it in `docs/DECISIONS.md` and raise it at the next gate. Do not silently deviate.
- Work in the phases of Section 7. **Stop at every GATE** and produce the gate packet (Section 9). The human relays packets to external reviewers (Claude in chat, ChatGPT) and brings feedback back.
- The project is an **experiment**. Its purpose is to find out whether the workstation helps, not to prove that it does.

---

## 1. Hypotheses and success criteria

The system is a *continual-adaptation layer* around existing models: it learns which strategies, models and memories work, without changing any model's weights.

| ID | Hypothesis | Comparison (held-out tasks, matched per-task budget) |
|----|------------|------------------------------------------------------|
| H1 | Collaboration + verification helps | Workstation-warm vs the **strongest simple baseline** |
| H2 | The environment learns | Workstation-warm (after the train stream) vs Workstation-cold (empty memory, default strategy) |
| H3 | Efficiency (secondary) | Cost per solved task, latency, calls |

**Falsification.** H1 is falsified if Workstation-warm is not better than the strongest baseline on held-out pass rate (paired 95% CI includes 0 or is negative). H2 is falsified if warm is not better than cold. Either outcome is a valid, publishable result.

**Not evidence of success:** many agents, big memory, elaborate strategies, a model saying the system is better, or an elegant architecture.

Write `docs/PREREGISTRATION.md` (metrics, arms, budgets, statistics, exclusion rules) and commit it **before** the first held-out run. Do not change it afterwards; amendments go in a dated addendum.

---

## 2. Principles

The six rules in `CLAUDE.md` are architectural law. Two further principles:

- **Separate learning speed from authority.** The learning plane may propose memories and strategies at high speed. It has no power to change the evaluator, the policy, permissions or the host.
- **Prefer measured consequences over model opinions.** Success signals ranked by trust: deterministic tests > static analysis > human review > independent model judges > self-evaluation. v0.1 uses deterministic tests only; model judges are not part of the success signal.

---

## 3. Scope

**Build:** Python orchestrator; provider abstraction (2 real providers + mock/replay); SQLite store; policy engine; sandboxed executor; separate-process evaluator; benchmark generator and validator; restricted strategy DSL and interpreter; layered memory with provenance and lifecycle; strategy registry with A/B, promotion, rollback; simple adaptive exploration; experiment runner for all arms; telemetry and automatic reports.

**Do not build in v0.1:** arbitrary self-modifying code; evaluator self-modification; evolutionary program search; autonomous web research; MCP/A2A integration; vector databases; distributed deployment or Kubernetes; fine-tuning; autonomous spending; production authentication; model-judge-based success signals.

---

## 4. Architecture

```
USER / BENCHMARK TASK
        │
   ORCHESTRATOR ──────────── POLICY ENGINE (default-deny; every action passes here)
        │                         │
   STRATEGY INTERPRETER           ├── budget / time / call limits
   (DSL, fixed operators)         ├── tool + path + network + model allowlists
        │                         └── memory namespace permissions
   MODEL ROUTER ── providers (A, B, mock/replay)
        │
   WORKSPACE (per-run, temp)
        │
   EXECUTOR (sandbox, visible-example tests only)
        │ submission
        ▼
   EVALUATOR  (separate process; hidden tests; returns pass/fail)
        │
   EXPERIENCE LOG (SQLite) ──► LEARNING ENGINE ──► candidates ──► A/B ──► promote / rollback
                                    │
                                 MEMORY (events → episodes → beliefs → lessons) + STRATEGY REGISTRY
```

Planes: **Control** (policy, evaluator definitions, permissions; human-changed only), **Learning** (proposes memories/strategies, runs experiments; cannot write to Control), **Execution** (models, executor, tools).

---

## 5. Experimental design

### 5.1 Task pools (strict separation)

| Pool | Size (min) | Purpose | Learning may use it? |
|------|-----------|---------|----------------------|
| PILOT | 30 | Debug harness, estimate cost, calibrate difficulty bands | No (never reused) |
| TRAIN | 150 | The experience stream the system learns from | Yes (full feedback) |
| VALIDATION | 100 | A/B tests, promotion and rollback decisions, ablations | Aggregate results only |
| HELD-OUT | 300 | Final reported results; run once per frozen state | **Never** |

Held-out results are never fed back into learning, memory, strategy selection or prompts. During the held-out run the workstation is **frozen**: memory read-only (warm) or empty (cold), no exploration, no promotion.

### 5.2 Arms

All arms get the same task statement, the same visible examples, the same executor for visible-example tests, and the same per-task budget cap.

- **A — Single shot:** one attempt, best single model.
- **B — Best-of-N:** same model, N independent samples, selected by visible-example test results (ties: first).
- **C — Single model + execute-and-repair loop:** one model, up to R rounds of repair using visible-test feedback. *This is the strong simple baseline; without it, any workstation gain could simply be execution feedback.*
- **D — Workstation-cold:** default strategy, empty memory.
- **E — Workstation-warm:** frozen state after learning on the TRAIN stream.

"Strongest simple baseline" = the best of A, B, C by validation score, chosen *before* the held-out run and recorded in the preregistration.

### 5.3 Budget matching

- Primary match: **dollar cost per task** (cap `BUDGET_USD_PER_TASK`, set from the pilot). Arms may spend less; report actual spend.
- Count *all* workstation spend: classifier, critics, mergers, failed attempts, repair calls, memory-summarizer calls at inference time.
- Also record and report model calls, input/output tokens, wall time and tool calls. Report accuracy-vs-cost at two or three budget levels if affordable (a Pareto view is more informative than one point).
- Use a pinned price table (`configs/prices.yaml`, dated). Record provider model IDs and versions on every call.

### 5.4 Statistics (preregistered)

- Paired by task. Primary metric: held-out hidden-test pass rate.
- Report paired difference with a 95% bootstrap CI and an exact McNemar test. Holm-correct across the two primary comparisons (E vs best baseline; E vs D).
- Rough power guide: with 300 paired tasks and 20–30% of tasks discordant, expect to detect a difference of about 7–9 percentage points. Smaller effects will be inconclusive; say so. If budget allows, increase HELD-OUT to 500.
- LLM output is stochastic. Fix temperatures in config. If budget allows, repeat each arm 2–3 times and report variance; otherwise state that run-to-run variance was not measured.
- Learning curve: process the TRAIN stream in blocks; after each block evaluate the frozen state on VALIDATION; plot validation accuracy against experience.

### 5.5 Contamination and leakage controls

- Fresh tasks only; do not use public benchmarks for the primary result.
- Generator-bias risk: tasks written by model family X may be easier for X. Use a generator from a different provider than at least one solver, and report per-provider pass rates.
- Put a unique canary string (GUID) in every held-out task file. A test must assert the canary never appears in prompts, memory, logs or strategy definitions.
- Held-out files live outside the learning plane's reachable paths and are never opened during development.
- Do not drop or reweight tasks based on workstation results. Difficulty bands are set from PILOT baseline results, in advance.

---

## 6. Component specifications

### 6.1 Providers
Interface `ModelProvider`: `generate()`, `get_model_id()`, `estimate_cost()`, `get_capabilities()`. Every call records provider, model ID/version, request ID, input/output tokens, estimated cost, latency, success/error. Include:
- Two real providers using whichever API keys the human has (ask in Phase 0).
- `MockProvider` (deterministic scripted outputs) for tests.
- A **record/replay cache** keyed by (model, prompt hash, params): replays make reruns free and reproducible. Replay mode is clearly labeled in telemetry and never used for final results unless the human approves.
- Orchestrator code must contain no provider-specific logic.

### 6.2 Secrets
Keys come from environment variables only. They never enter prompts, memory, strategies, logs, SQLite, git or reports. The executor child process gets an **explicitly constructed** environment (no inherited variables). Test this.

### 6.3 Policy engine
Deterministic, default-deny, outside any model. Evaluates `(actor, action, resource, context)` → ALLOW/DENY with a logged reason. Controls: filesystem paths, subprocesses, network, tools, models, memory namespaces, max runtime, max calls, max tokens, max estimated spend. Strategies request; the policy decides. The policy file is part of the Control plane: read-only to the learning plane and changed only by the human. Because the policy engine runs in the orchestrator process, the only *untrusted code* it must contain is model-generated code, which runs in the executor, never in-process.

### 6.4 Executor (sandbox)
Detect the OS in Phase 0 and report the achievable isolation level. Record `isolation_level` in every experiment record.
- **Linux/macOS:** subprocess in a fresh temp dir, explicit minimal environment, `resource` limits (CPU, memory, processes, file size), wall-clock timeout, and network disabled via OS tools (e.g. `unshare`/`bwrap`/`firejail`) when available.
- **Windows:** Job Object limits for memory/processes/time; if network isolation cannot be enforced, prefer WSL2 or a container if the machine can run it comfortably. A weak PC may not.
- If strong isolation cannot be provided, **disable arbitrary execution** and tell the human. A static import denylist is defense-in-depth only, never the boundary.
- The executor interface must be replaceable (Docker later).
- The workstation's executor runs **visible-example tests only**. Hidden tests exist only inside the evaluator.

### 6.5 Evaluator
Separate process, communicating over stdin/stdout JSON. Immutable config per experiment, with a version. Read-only access to hidden tests; no network; own sandbox for running submissions. Returns pass/fail (plus task category). For TRAIN tasks it may also return failing visible-test messages; for VALIDATION only aggregate and pass/fail; for HELD-OUT pass/fail only, written to a results store the learning plane cannot read. Evaluator changes → new version → full re-baseline; never compare scores across evaluator versions. The system may file an *evaluator concern ticket* (`docs/evaluator_tickets/`) but can never edit evaluator code, tests or tasks.

### 6.6 Benchmark
Programming tasks with deterministic tests across categories: arrays, strings, hash maps, sorting/search, recursion, graphs, dynamic programming, greedy, data structures, numerical. Each task: ID, content hash, category, difficulty estimate, statement, I/O spec, visible examples, hidden tests, reference solution.

Generation and validation pipeline (generated tasks are **not trusted** until validated):
1. Generator model writes statement, reference solution and a test generator.
2. An independent solution (different model family if possible) must agree with the reference on all tests; use brute-force oracles where feasible.
3. Test-strength check: simple mutants of the reference (off-by-one, wrong comparator) must fail at least one hidden test.
4. Deduplicate by content hash and n-gram similarity.
5. Human spot-check by Ridha of a random sample of ~30 tasks (clarity, correctness) before first use.
6. Canary GUIDs added to held-out files; benchmark version and hash recorded.

### 6.7 Strategy DSL
Declarative (YAML/JSON), validated against a schema. **Not Python.** Operators: `CLASSIFY`, `CALL_MODEL`, `PARALLEL`, `MERGE`, `VERIFY`, `REPAIR`, `FINALIZE`. A strategy specifies the operator graph, model IDs, **prompt-template IDs** from a version-controlled template library (learned strategies do not write free-form prompts in v0.1), max calls, timeout, allowed tools and verification method. The validator rejects unknown operators/fields, cycles beyond a bounded repair loop, and anything requesting capabilities the policy does not grant. Candidate generation in v0.1 = parameter mutation (model choice, N, repair rounds, template choice, verifier) plus LLM-proposed variants that must pass the validator. Initial default strategy:
`CLASSIFY → PARALLEL(solver A, solver B) → MERGE/CRITIC → VERIFY (execute visible tests) → REPAIR if failed → FINALIZE`. Simpler strategies must be able to win.

### 6.8 Memory
Layers: **raw events** (short TTL) → **episodes** (structured attempt records) → **beliefs** (hypotheses with confidence) → **lessons** (supported generalizations). Strategies live in the registry. Item fields: ID, type, content, source, source hash, timestamp, model/version, domain/category, supporting experiment IDs, derived-from edges, confidence, status (`ACTIVE`/`ARCHIVED`/`QUARANTINED`), verification status, last-tested time, retest/expiry date.
- **Independence:** support is counted over distinct root sources with no derived-from path between them. Copies and re-uses of one source count once. Hash content to detect copies.
- **Trust pipeline:** model output → candidate → evidence → verification → belief → repeated independent support + positive ablation → lesson. Default promotion rule (configurable in `configs/learning.yaml`): ≥3 independent supporting episodes **and** a VALIDATION ablation (memory-on vs memory-off for that category) showing a non-negative effect with no category regression > 3 points.
- **Retrieval:** SQLite FTS5 plus category filter. Only `ACTIVE`, verified lessons/beliefs are retrievable. Injected into prompts as clearly delimited reference data, capped at K items, never as instructions. Log `memory_used` for every run to enable ablations.
- **Forgetting:** scheduled consolidation merges duplicates; items unused or unhelpful for a window are archived; model/tool version change marks relevant items `UNVERIFIED` until retested; items correlated with worse outcomes are quarantined (rate-limited, with an alert on spikes). Never delete evidence of a poisoning event; quarantine it.

### 6.9 Learning, promotion, rollback, exploration
What v0.1 learns: which strategy and model per task category; which verification catches errors; which memories transfer; which strategies fail repeatedly. Nothing else.
- **Lifecycle:** CANDIDATE → SHADOW (runs on VALIDATION tasks without affecting results) → A/B (random assignment on VALIDATION) → PROMOTED → MONITORED → ARCHIVED/ROLLBACK/QUARANTINE.
- **Promotion:** paired CI lower bound on solve-rate difference > 0 versus the incumbent, no category regression beyond threshold (n ≥ 10 per category), cost per solved task not worse than 1.5× unless justified by a significant gain, and zero policy violations.
- **Rollback:** after two consecutive monitoring windows where the 95% CI of (new − previous) lies below 0. Any policy or security violation → immediate quarantine. Never roll back on a single noisy window. Keep the previous version available.
- **Exploration:** contextual-bandit style (e.g. Thompson sampling per category). Exploration share rises when confidence is low, drift is flagged (model version change, rollback) or a category is poorly understood, and falls when posteriors concentrate. Capped per task by budget. Active **only** on the TRAIN stream; zero on HELD-OUT.
- Compare against a no-learning control: same TRAIN stream, memory writes disabled, to separate "more samples" from "learning".

### 6.10 Telemetry
Every run emits a JSON record and a SQLite row: experiment_id, arm, task_id, pool, strategy_id/version, model_id/version, prompt/template version, evaluator_version, benchmark_version, isolation_level, seed, temperature, budget_cap, start_time, latency, input/output tokens, model calls, tool calls, estimated cost, final result, verification result, failure reason, memory_used, memories_created, strategy outcome, replay flag.

### 6.11 Reports
Auto-generated into `reports/`: quality (pass rate overall and by category, error types), efficiency (cost per solved task, latency, tokens, calls), learning (learning curve, warm vs cold, memory ablation, promoted/rejected strategies, transfer to unseen categories), reliability (variance, regressions, rollbacks, evaluator tickets). The final report compares all arms with CIs and states plainly which hypotheses held.

---

## 7. Phases and gates

Security comes **before** any model-generated code executes.

| Phase | Work | Exit criteria |
|-------|------|---------------|
| 0 | Repo, `.gitignore`, `.env.example`, config, CI (`pytest`), `docs/DECISIONS.md`, `docs/QUESTIONS.md`; detect OS and isolation capability; ask the human the Section 10 questions | Questions answered; dev safety configured |
| 1 | SQLite schema, telemetry, provider interface, mock/replay provider, two real providers, budget accounting | Tests pass; no secret in any output |
| 2 | Policy engine + executor sandbox + security tests | All security tests pass. **GATE 1** |
| 3 | Benchmark schema, generator, validation pipeline, three pools + pilot, canaries | Spot-check by the human passed. **GATE 2** |
| 4 | Evaluator process; arms A, B, C; pilot run on PILOT with cost estimate | Pilot report with budget recommendation. **GATE 3** (human approves spend) |
| 5 | Strategy DSL, validator, interpreter, default workstation strategy (arm D) | Arm D runs end-to-end on PILOT |
| 6 | Memory layers, provenance, independence, lifecycle, quarantine, retrieval | Memory tests pass |
| 7 | Strategy registry, A/B, promotion, rollback, adaptive exploration, monitoring | Tests pass; dry run on PILOT |
| 8 | Learning loop over the TRAIN stream with learning curve + no-learning control | **GATE 4** (independent review before the final experiment) |
| 9 | Freeze state; commit preregistration; run HELD-OUT for all arms (cold + warm) | Results stored; no learning during run |
| 10 | `docs/ARCHITECTURE_REVIEW.md` and `docs/EXPERIMENT_REPORT.md` | **FINAL GATE** |

Do not start a phase before the previous exit criteria are met.

---

## 8. Required tests (write before the code they cover)

Policy denial; policy allowlist; unknown action denied; API key never persisted or logged; child-process environment is clean; executor timeout, memory limit and no-network behavior (or documented gap); budget enforcement (calls, tokens, dollars, time); memory provenance recorded; duplicate-source detection; independence counting with derived-from edges; quarantine excludes items from retrieval; strategy DSL rejects unknown operators and permission escalation; strategy versioning and rollback; evaluator runs in a separate process and strategies cannot import or modify it; held-out files unreachable from the learning plane; canary never appears in prompts/memory/logs; benchmark immutability (hash check); held-out run is frozen (no memory writes, no exploration); replay results are flagged.

---

## 9. Review protocol (how Claude Code, Claude and ChatGPT improve this together)

Claude Code cannot talk to Claude in chat or to ChatGPT directly, so the human relays. At every gate:

1. Claude Code writes `docs/gates/GATE-N.md`: what was built, tests run and results, deviations from the plan, open risks, spend so far, and three specific questions for reviewers.
2. Claude Code starts a **fresh-context reviewer subagent** that has not seen the build conversation. Its instruction: read the plan and the code and try to break it. Its findings are pasted verbatim into the gate packet. (A model reviewing its own work in the same context is biased.)
3. The human gives the packet to Claude (chat) and to ChatGPT, and saves their replies under `docs/external_review/`.
4. Claude Code answers every point as ACCEPT / REJECT (with reasons) / DEFER in `docs/DECISIONS.md`, then implements what was accepted.

At the end, write `docs/ARCHITECTURE_REVIEW.md` answering: (1) which assumptions are probably wrong; (2) which parts add needless complexity; (3) where the system can fool itself; (4) where memory can become harmful; (5) how the evaluator can be gamed; (6) where equal-budget comparisons are still unfair; (7) the weakest security boundary; (8) what to remove from v0.1; (9) which research suggests a better design (cite sources and say how confident you are); (10) which experiment would falsify the core hypothesis. Document criticism first, then implement only clearly justified changes.

---

## 10. Questions Claude Code must ask the human in Phase 0

1. Which operating system and how much RAM/CPU does the development machine have? (Determines the sandbox.)
2. Which two model providers and models do you have API access to? Do the keys have provider-side spend limits?
3. What is the total experiment budget and `MAX_RUN_COST_USD`?
4. Can you spot-check ~30 generated tasks, and how much time can you give per gate?
5. Is it acceptable to start with Python-only tasks?

---

## 11. Deliverables

Working code and tests; the benchmark with versions and hashes; `docs/PREREGISTRATION.md`; `docs/DECISIONS.md`; gate packets and external reviews; `reports/` with all arms compared; `docs/ARCHITECTURE_REVIEW.md`; `docs/EXPERIMENT_REPORT.md` (what was implemented, what was tested, what failed, and what evidence supports each conclusion).

The first goal is not to build AGI. It is to build a measurable environment that can prove or disprove that continual adaptation around existing models gives useful gains.
