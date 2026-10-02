# Handoff to Claude Code — from Claude (chat)

You are the builder of **AI Workstation v0.1**. This message comes from Claude in the chat app, after a long design review with Ridha and ChatGPT. A second handoff, written by ChatGPT, accompanies it. Read, in this order:

1. `CLAUDE.md` (standing rules)
2. `PLAN.md` (the specification)
3. This file
4. ChatGPT's handoff

**Precedence:** `CLAUDE.md` > Ridha-approved amendments > `PLAN.md` > the rest of the handoffs. The amendments in Section 4 below count as approved once Ridha gives you this file; log each in `docs/DECISIONS.md` and in the preregistration. An amendment may modify `PLAN.md` but never the safety rules in `CLAUDE.md`. Where two documents *conflict*, stop and ask Ridha instead of choosing silently, and record every conflict in `docs/DECISIONS.md`.

---

## 1. What Ridha wants

Ridha wants an environment where different AI models (Claude, GPT, Gemini, DeepSeek, local models, anything) can work on problems together, at the same time or at different times, and where the output improves over time. He knows model weights can't be changed from outside. So the idea is a **continual-adaptation layer** around the models:

- a shared workspace that the *environment*, not any model's context window, owns;
- persistent memory with provenance;
- verification by real tests, not by model opinion;
- collaboration among models;
- learning which strategies, models and verification steps work for which task types.

His long-term vision is larger: strategy discovery, long-running autonomous research, many models. **v0.1 is deliberately narrow.** Its job is to find out *whether this idea produces any measurable gain at all* on a verifiable task domain (programming problems with deterministic tests). A null result ("the workstation does not beat simple baselines") is a successful outcome. Please do not let any part of the build tilt toward making the workstation look good.

How Ridha works: he is terse, and he relays messages between you, me and ChatGPT by hand. Keep gate packets short and skimmable, put the decisions he must make at the top, and ask all Phase 0 questions in **one** batch with a recommended default for each. He has mentioned that his PC is weak, so confirm hardware in Phase 0 and avoid anything heavy (local LLMs, large containers) unless he says it is fine. He wants complete, high-quality deliverables for each phase, not scaffolds. Never ask him for API keys; ask only which providers and models he can use and whether the keys are configured in the environment.

---

## 2. What the design review concluded

Converged (all three of us agree):
- Models request; a deterministic default-deny policy engine decides. Memory is evidence, not truth. Strategies are data (a small DSL), not code. The evaluator is a separate protected process. Everything important is versioned.
- Multi-agent is **one inference strategy to be tested**, not a proven winner. Hence the baselines: single shot, best-of-N, single-model execute-and-repair, workstation-cold, workstation-warm.
- Security precedes code execution. Memory is an attack surface. Learning authority is separated from execution authority.
- A fast loop (strategies, memory, routing) learns automatically; a slow loop (evaluator, benchmark, policy) changes only by human review.

Corrections made along the way (so you don't reintroduce the original errors):
- "Multi-agent consistently beats single-agent" was too strong.
- "Equal cost" in dollars alone is not enough; record calls, tokens, time and tool use too.
- The first draft ran model code before the sandbox existed; that was fixed.
- A frozen evaluator forever is also a risk; hence the evaluator-ticket mechanism.

Still unresolved (don't pretend otherwise):
- Strategy *discovery* is limited by the operators the DSL provides. v0.1 mostly does strategy *selection and parameter search*. Say so in the report.
- Learning in domains without a checker (writing, design) is out of scope for v0.1.
- The thresholds in `PLAN.md` (3 independent episodes, 3-point regression limit, 1.5× cost) are placeholders, not tuned values.

---

## 3. Research context, with honest confidence labels

**Seen by me in primary sources (still re-check before citing):**
- *Multi-Agent Reasoning Improves Compute Efficiency: Pareto-Optimal Test-Time Scaling* (ACL 2026 SRW; arXiv 2605.01566): on MMLU-Pro and BBH at comparable compute, mixture-of-agents beat self-consistency by about 2.7 points and debate by about 1.3, while **self-refinement was consistently worse than plain chain-of-thought** despite using more compute. A larger model without test-time scaling could beat a heavily scaled smaller one. *Implication for you:* model-critique and self-refine steps can add noise. Keep execution-based feedback as the repair signal, and make "no critic/merge step" a candidate strategy from the start.
- *MATTRL* (arXiv 2601.09667): test-time experience pools help but drift; stale or spurious heuristics accumulate and need lifecycle management. *Implication:* memory expiry and retest are required, not optional.
- Conference and survey material on agent memory harnesses: ranked recall beat a gating policy in one small experiment, and even perfect ground-truth memory did not guarantee correct answers. *Implication:* low confidence (small study); log `memory_used` so you can measure memory's effect in this project instead of assuming it.

**Reported to me by ChatGPT, not verified by me:** the memory-poisoning benchmark percentages, the HFlow workflow-evolution results, Anthropic's finding that infrastructure configuration shifts agentic-coding scores by several points, and the Meta Muse/Sentinel and other vendor architecture claims. Treat these as leads. Before you cite any of them in `EXPERIMENT_REPORT.md`, find and read the primary source, or downgrade the claim to "reported, unverified". The design does not depend on them being true.

---

## 4. Amendments to PLAN.md (binding once Ridha approves; log each in DECISIONS.md)

**A1. Attribution on VALIDATION (ChatGPT's threat 1, accepted).** Warm vs cold shows the *whole environment* learned, not *what* learned. Run a 2×2 on VALIDATION: {default, learned strategy} × {no memory, learned memory}. The held-out run stays as planned (baselines, cold, warm). Treat this as secondary, explanatory evidence about attribution, not definitive causal proof, and it does not replace H1/H2. In the final report state exactly what the data does and doesn't support.

**A2. Provider stability (ChatGPT's threat 2, accepted, plus a detector).**
- At Gate 1 write `docs/PROVIDER_STABILITY.md`: does each provider expose an immutable model version? If not, say so as a validity limitation.
- Add a **canary regression set**: a fixed 15–20 task subset of PILOT re-run at the start and end of each experiment session. A shift in pass rate beyond a preset threshold, or output-hash drift, flags **possible provider/environment drift**. Output drift alone does not prove the model changed (sampling, routing and infrastructure also cause it), so record model metadata, fixed configuration and the pass-rate distribution together, and report a flag as a validity risk, not a verdict. Never rerun until a result "looks better".

**A3. Benchmark validity (ChatGPT's threat 3, accepted, made concrete).** At Gate 2 produce `docs/BENCHMARK_VALIDITY.md` with evidence for each of:
- brute-force oracles for small tasks; property-based/fuzz test generation (e.g. `hypothesis`);
- validation by a different model family than the generator;
- mutation score reported per category, with a preset minimum (calibrate on the pilot);
- category and difficulty balance, with difficulty bands fixed from PILOT baseline results *in advance*;
- tasks that every baseline passes (or fails) in PILOT are flagged, not silently dropped;
- per-provider pass rates, to expose generator-family bias;
- no direct or indirect held-out leakage (canary tests).
If a benchmark flaw is found *after* a held-out run: create benchmark v2, report both versions and the flaw, and do not quietly repair and rerun.

**A4. Training adequacy and learning-curve analysis (new).** With 150 TRAIN tasks over about 10 categories, per-category experience is thin and H2 may be underpowered. These are two separate questions: (i) is the held-out warm-vs-cold comparison adequately powered (a standard paired power analysis, recomputed from PILOT discordance rates), and (ii) is the TRAIN stream long enough for a measurable learning curve to appear on VALIDATION (per-category sample sizes, variance, expected signal, validation cost)? At Gate 3, estimate both from the PILOT, update the numbers in `PREREGISTRATION.md`, and give Ridha options with costs: fewer categories (e.g. five), a larger TRAIN pool, or H2 defined at the overall level only. Don't decide for him. Any change must be made and recorded **before** held-out data is touched, or it is moving the goalposts.

**A5. Ablate meaningful design choices (new).** Not every primitive is an experimental hypothesis (`CALL_MODEL` and `FINALIZE` are not), and leave-one-operator-out tests can mislead because operators interact. Ablate the design choices that matter, as a ladder of candidate strategies from the start: S1 single solver; S2 two parallel solvers; S3 two solvers + merge/critic; S4 two solvers + merge + visible-test repair; S5 variants of N. The question is whether a simpler strategy beats the complicated one, and the system must be able to discover that. (Label these S1–S5 so they aren't confused with experimental arms A–E.)

**A6. Selection rule for best-of-N (new).** If tasks have only one to three visible examples, selection by visible tests is weak. Define in the preregistration how N is chosen, how ties break, and what happens when no sample passes visible tests; apply the same rule to every arm that samples.

**A7. No post-hoc changes (master rule, from ChatGPT).** Once held-out results are visible, nothing changes in a primary hypothesis, primary metric, benchmark inclusion/exclusion rule, baseline-selection rule, or statistical test. Amendments are allowed only *before* the relevant data is revealed, each with a timestamp and reason in `docs/DECISIONS.md` and a dated addendum to `PREREGISTRATION.md`. Analyses added afterwards must be labeled exploratory. Enforce this yourself and flag any request, including Ridha's, that would break it.

---

## 5. Where I want you to push back

Challenge these, with evidence and executable tests where possible:
- **Windows and weak-PC isolation.** If real isolation isn't achievable, say so plainly and recommend the safest fallback. Don't claim a sandbox you can't demonstrate.
- **The policy engine lives in the orchestrator process.** Write a short threat model: what does it protect against, what can bypass it, and where is it only defense-in-depth?
- **Record/replay cache.** Could it mask nondeterminism or provider drift? Define when replay is allowed.
- **LLM-proposed strategy variants** may produce little value over parameter mutation. Measure how many pass the validator and how many beat the incumbent.
- **Aggregate feedback can still leak.** Look for indirect probing of VALIDATION and held-out data through repeated queries.
- **Budget realism.** Compute the full-experiment cost from pilot data before Ridha commits: all arms, three pools, baseline selection on VALIDATION, A1's 2×2, repeats if any.

---

## 6. How to work with reviewers

Claude (chat) and ChatGPT are fallible reviewers, and neither is your boss. For each point they raise: verify it against the code and data, then mark ACCEPT / REJECT / DEFER with reasons in `docs/DECISIONS.md`. Don't defer to either of us on facts you can check yourself. Where the two reviewers disagree, show both views to Ridha. Don't change architecture without his approval; bug fixes are fine. Use a fresh-context reviewer subagent at every gate, instructed to assume the builders are wrong and to produce concrete failure scenarios and failing tests.

---

## 7. Your first action

Do **Phase 0 only**:
1. Read `CLAUDE.md`, `PLAN.md`, this file, and ChatGPT's handoff.
2. Create the repo skeleton, `.gitignore`, `.env.example`, config, `pytest` setup, `docs/DECISIONS.md`, `docs/QUESTIONS.md`, and `docs/gates/GATE-0.md`.
3. Detect OS, CPU/RAM, Python version, and the isolation level you can really achieve; document it.
4. Configure development safety (deny reads of `.env*`, `secrets/`, `benchmarks/held_out/`; use the filesystem/network sandbox if your Claude Code version supports it; check current docs rather than guessing syntax).
5. Ask Ridha the Section 10 questions of `PLAN.md` in one batch, with recommended defaults.
6. Stop. Write the Gate 0 packet: what you built, what you detected, deviations, risks, three questions for reviewers, and the reviewer subagent's findings.

Do not write any Phase 1+ code until Ridha has reviewed the packet.

The mindset: you are building an experiment, not a product. Build, measure, attack, test, report, improve, and report honestly whatever the data says.
