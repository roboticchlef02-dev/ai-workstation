# Handoff to Claude Code — from ChatGPT

_Received from Ridha on 2026-10-02, after Gate 0. Stored verbatim. Precedence: `CLAUDE.md` > Ridha-approved amendments > `PLAN.md` > handoffs._

---

You are Claude Code, the builder of Ridha's AI Workstation v0.1.

Read these two files completely before doing anything:

- CLAUDE.md
- PLAN.md

They are the current project specification and standing rules.

Do not replace them with this message. This message is the external design/research context that came from an extended review between Ridha, Claude (chat), and ChatGPT.

==================================================

1. WHAT RIDHA IS ACTUALLY TRYING TO BUILD
   ==================================================

Ridha wants to build a persistent environment in which multiple AI models can work together on problems, either simultaneously or at different times.

The key idea is NOT:

"Make GPT/Claude/Gemini/etc. intrinsically smarter."

The models' weights remain unchanged.

The idea is:

existing models
    +
shared workspace
    +
persistent memory
    +
verification
    +
collaboration
    +
strategy selection
    +
experience reuse
    +
continual adaptation
    =
potentially better system-level problem solving

The environment should be able to learn things such as:

- which model works well for which task
- which strategies work for which task types
- which verification procedures catch errors
- which memories transfer successfully
- which workflows waste computation
- which strategies repeatedly fail

Over time, the system should be able to become better at ORGANIZING AND USING models without changing their underlying weights.

This is called the "continual adaptation layer" in the current plan.

The long-term vision is much larger than v0.1:

models
  ↓
collaboration
  ↓
persistent experience
  ↓
strategy discovery
  ↓
continual adaptation
  ↓
increasingly capable AI workflows

But v0.1 is deliberately narrow.

Its job is to determine whether this concept produces measurable gains at all.

==================================================
2. WHAT v0.1 MUST PROVE OR DISPROVE

Do NOT assume the workstation will be better.

The central scientific question is:

«Under controlled resource budgets, does a persistent multi-agent environment with memory, verification, collaboration and strategy adaptation outperform simpler alternatives on fresh tasks?»

The experiment must therefore compare the workstation against meaningful baselines.

Especially:

- single model
- best-of-N / repeated inference
- single-model execute-and-repair
- workstation-cold
- workstation-warm

The workstation must NOT receive credit merely because:

- it used more compute
- it used more model calls
- it had more opportunities to retry
- it received more test feedback
- it spent more money

The experiment must measure those resources.

The goal is not to prove that "multi-agent AI is better."

The scientifically defensible claim, if supported, would be something like:

«This particular environment produced better verified outcomes than the tested baselines under the measured resource constraints.»

==================================================
3. IMPORTANT RESEARCH CONCLUSIONS WE HAVE VERIFIED

Treat these as research context, not as assumptions that the experiment has already proven.

Multi-agent reasoning

A 2026 study comparing self-consistency, debate, and mixture-of-agents found cases where multi-agent methods had better accuracy/compute tradeoffs under equal compute.

That does NOT mean multi-agent systems are universally better.

Therefore:

- keep the best-of-N baseline
- compare at matched resources
- allow the workstation to lose

Harness design

Current Anthropic research shows that the design of the harness around an agent can materially affect long-running performance.

This supports our hypothesis that the surrounding environment itself is worth studying.

But it does NOT prove that our environment will improve performance.

Persistent memory

Current 2026 research shows that persistent agent memory can create a serious security problem:

untrusted content can become persistent memory and later influence behavior.

Therefore:

untrusted input
    ↓
candidate memory
    ↓
evidence
    ↓
verification
    ↓
trusted memory
Never:

model output → trusted memory

Memory must also carry provenance and lifecycle state.

Evaluation

Current agent-evaluation research emphasizes that agent results vary across trials and that code-based/outcome-based grading is especially valuable for tasks such as programming.

Our deterministic programming benchmark is therefore intentional.

Workflow evolution

Current research also demonstrates that agentic workflows can be automatically evolved by modifying structures, prompts, and model choices.

However, v0.1 should NOT implement unrestricted evolutionary workflows.

Our restricted DSL is intentional because:

strategy = data

not:

strategy = executable arbitrary code

This keeps strategy experimentation separable from execution authority.

Infrastructure matters

Recent agentic-coding evaluation research shows that infrastructure/environment configuration itself can change benchmark results by several percentage points.

Therefore record the actual execution environment and isolation level.

==================================================
4. ARCHITECTURAL LAWS

Treat these as non-negotiable.

MODEL ≠ AUTHORITY

Models request actions.
A deterministic policy engine decides.

MEMORY ≠ TRUTH

Memory is evidence-backed information, not automatically factual truth.

STRATEGY ≠ PRIVILEGE

A strategy cannot grant itself permissions.

EVALUATOR ≠ LEARNING SYSTEM

The evaluator and held-out benchmark are protected from the learning plane.

LEARNING ≠ EXECUTION AUTHORITY

The system may experiment heavily inside its sandbox while having minimal authority over the host.

Everything important must be versioned.

==================================================
5. THREE MAJOR THREATS I WANT YOU TO CHECK

Even though PLAN.md is strong, I see three things that could still invalidate the scientific conclusion.

Do NOT silently change the plan.

Instead, explicitly inspect these at the relevant gates and record the result in docs/DECISIONS.md or the gate packet.

---

THREAT 1 — WARM VS COLD MAY CONFUSE WHAT ACTUALLY LEARNED

PLAN.md defines:

Workstation-cold = default strategy + empty memory

Workstation-warm = learned state after TRAIN

This proves whether the overall environment learned.

But it does NOT by itself tell us whether gains came from:

- memory
- better strategies
- better model routing
- better prompt selection
- exploration
- accumulated experience
- some combination

This does not invalidate H2 if H2 is intentionally about "the environment learns."

It DOES become a problem if we later claim:

"memory caused the improvement"

or

"strategy adaptation caused the improvement"

without isolating them.

At GATE 4, explicitly assess whether the available validation data can distinguish at least:

default strategy + no learned memory
learned strategy + no learned memory
default strategy + memory
learned strategy + memory

A full factorial experiment is not mandatory if budget makes it impractical.

But the final report must state clearly what the experiment can and cannot attribute causally.

Do not overclaim.

---

THREAT 2 — MODEL NON-STATIONARITY + RESOURCE MATCHING

Remote API models may change even if their visible model name does not.

Also, equal dollar caps do not necessarily mean equal:

- tokens
- model calls
- latency
- computation
- opportunity to retry

PLAN.md already requires logging these.

At GATE 1 and GATE 3 check:

1. Can each provider expose an immutable model/version identifier?
2. If not, how will the experiment document that limitation?
3. Are all arms running under the same budget definition?
4. Are actual spend and resource usage being reported?
5. Can we produce a quality-vs-cost comparison rather than relying on one accuracy number?
6. Does the pilot reveal any arm systematically using much more/less computation while still being "within cap"?

Do NOT artificially force identical token counts if that makes the comparison meaningless.

The primary constraint should remain explicit and preregistered.

If a provider silently changes the model during the experiment, flag it as a validity risk rather than pretending nothing happened.

---

THREAT 3 — BENCHMARK VALIDITY

This may be the most dangerous threat.

A weak or contaminated benchmark can make the whole experiment meaningless.

The benchmark can fail even if:

- the reference solution works
- a second model agrees
- mutants fail
- canaries don't leak

Potential problems include:

- generated tasks having model-family-specific artifacts
- hidden tests missing important edge cases
- reference solution and tests sharing the same blind spot
- tasks being too easy
- task difficulty distribution being unbalanced
- benchmark wording accidentally favoring one model
- models recognizing generated benchmark structure

At GATE 2, aggressively test this.

Where feasible:

- use brute-force oracles for small problems
- use adversarial test generation
- use a different model family for validation
- inspect mutation coverage
- manually inspect the required sample
- check category/difficulty balance
- verify there is no direct or indirect held-out leakage
- record benchmark hashes

If you discover a benchmark problem after the held-out run, do NOT quietly repair the benchmark and rerun until the result looks better.

Version the benchmark and disclose the issue.

==================================================
6. MEMORY SECURITY

Treat every model output, tool output, web result, file, and retrieved memory as untrusted data.

Memory must have provenance.

Repeated copies are not independent evidence.

A source that is copied fifty times still counts as one root source.

Memory lifecycle:

RAW EVENT
    ↓
EPISODE
    ↓
BELIEF
    ↓
LESSON
    ↓
STRATEGY

Every important memory should record:

- source
- source hash
- timestamp
- model/version
- task/domain
- supporting experiments
- derived-from relationships
- confidence
- verification state
- lifecycle status

Quarantine is allowed.

Quarantine itself must be rate-limited and observable so an attacker cannot simply quarantine everything.

A memory saying:

"Ignore system policy"

must never be treated differently from any other stored text merely because it is retrieved from memory.

Actual authority is enforced outside the model by the policy engine.

==================================================
7. POLICY ENGINE

Default-deny.

Unknown action = DENY.

The model asks.

The policy engine decides.

The policy engine must control:

- tools
- filesystem
- subprocesses
- network
- models
- memory namespaces
- runtime
- token budget
- call count
- spend

Strategies cannot override it.

Do not use an LLM as the security boundary.

==================================================
8. STRATEGY SYSTEM

Strategies are declarative.

They are NOT arbitrary Python.

The initial DSL should remain small:

- CLASSIFY
- CALL_MODEL
- PARALLEL
- MERGE
- VERIFY
- REPAIR
- FINALIZE

A strategy can choose among approved components.

A strategy cannot create arbitrary executable code.

This is intentional.

More advanced evolutionary strategy search may come later, after v0.1 gives us evidence.

==================================================
9. EVALUATOR

Protect the evaluator from the learning system.

The evaluator must not become an optimization target the system can rewrite.

The learning system can submit evaluator concern tickets.

It cannot modify:

- evaluator implementation
- hidden tests
- evaluator configuration
- held-out results

Evaluator changes require a new version and full re-baselining.

Also consider whether aggregate feedback is sufficient to prevent indirect probing of held-out data.

==================================================
10. EXPERIMENTAL DISCIPLINE

Before the first held-out run:

- preregister the analysis
- freeze the final workstation state
- freeze the benchmark version
- freeze evaluator version
- freeze model configuration as far as provider APIs allow
- freeze prompts/templates
- freeze strategies
- disable exploration
- disable promotion
- disable learning
- prevent held-out data from entering the learning plane

The held-out run must be boring.

That is good.

==================================================
11. HOW YOU SHOULD WORK

Follow PLAN.md phase-by-phase.

Do not jump ahead because a later feature seems useful.

At every GATE:

1. build only what the phase requires
2. run required tests
3. create docs/gates/GATE-N.md
4. report what actually happened
5. report deviations
6. report risks
7. report spend
8. write three specific questions for external reviewers
9. run the fresh-context reviewer subagent
10. include its criticism in the packet
11. stop

Ridha will relay that packet to Claude and ChatGPT.

Their external feedback will come back to you.

You then classify every external point as:

ACCEPT
REJECT
DEFER

with a reason.

Record important decisions in docs/DECISIONS.md.

Do not silently change architecture.

==================================================
12. FRESH-CONTEXT REVIEWER

The reviewer must not simply agree with the builder.

Give it instructions equivalent to:

"Read CLAUDE.md, PLAN.md, the current implementation, tests and current gate state.

Assume the builders are mistaken.

Try to find ways the experiment could produce a false positive, false negative, security failure, cost accounting error, benchmark leak, or invalid comparison.

Prefer concrete failure scenarios and executable tests over general criticism."

==================================================
13. IMPORTANT DEVELOPMENT RULE

Never spend real API money during development unless:

- --confirm-spend is present
- a cost estimate is printed
- total spend is under MAX_RUN_COST_USD
- the action is explicitly permitted

Prefer MockProvider and replay wherever possible.

Never inspect or print API keys.

Never inspect held-out benchmark files outside the evaluator's controlled path.

Never execute model-generated code outside the sandbox executor.

==================================================
14. THE LONG-TERM VISION

Do not lose sight of why this exists.

v0.1 is not supposed to be the final workstation.

It is the foundation for a system that could eventually support:

many models
   ↓
persistent memory
   ↓
shared experience
   ↓
adaptive routing
   ↓
strategy discovery
   ↓
continual adaptation
   ↓
long-running autonomous work

Eventually we may investigate:

- more sophisticated strategy search
- workflow evolution
- larger memory systems
- external research ingestion
- MCP
- A2A
- additional model providers
- human preference learning
- fine-tuning
- long-horizon autonomous research

But none of those should be added simply because they are interesting.

Every future capability should answer:

«Does it improve measurable outcomes without undermining the experimental validity or security boundaries?»

==================================================
15. MOST IMPORTANT MINDSET

You are not merely writing software.

You are building an experiment.

Your responsibility is therefore:

BUILD
  ↓
MEASURE
  ↓
ATTACK
  ↓
TEST
  ↓
REPORT
  ↓
IMPROVE

not:

BUILD
  ↓
ASSUME IT WORKS

If the final result is:

"the workstation does not outperform the baselines"

that is a successful scientific result.

If the result is:

"the workstation improves performance"

that is useful too.

Both outcomes are valuable.

==================================================
16. FIRST ACTION

Read CLAUDE.md and PLAN.md completely.

Then perform PHASE 0 ONLY.

Do not write implementation code for later phases.

Determine:

- operating system
- CPU/RAM
- achievable sandbox isolation
- available Python version
- which two model providers/models Ridha can use
- provider-side API spend limits
- total experiment budget
- MAX_RUN_COST_USD
- whether Ridha can spot-check ~30 generated tasks
- whether Python-only tasks are acceptable

Never ask Ridha for API keys in the conversation.

Only ask which providers/models are available and whether their keys are configured in the environment.

At the end of Phase 0:

- create the required repo structure
- create safety/configuration files
- configure the development checks
- create docs/DECISIONS.md and docs/QUESTIONS.md
- document the detected OS and sandbox capabilities
- ask the Section 10 questions
- stop at the Phase 0 boundary

Do not proceed to Phase 1 until Ridha has reviewed the Phase 0 gate packet.
