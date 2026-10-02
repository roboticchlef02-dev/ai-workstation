# Gate 0 — external review by ChatGPT

_Relayed by Ridha on 2026-10-02. Stored verbatim. This is a reviewer's opinion, not Ridha's decision. Classification is in `docs/DECISIONS.md` → "External review — Gate 0 (ChatGPT)"._

---

I reviewed the uploaded `CLAUDE.md`, `PLAN.md`, the Claude-chat handoff, and the actual `GATE-0.md` packet from the repository. The core design is strong: the experiment is explicitly meant to be falsifiable, with protected evaluation, default-deny authority, versioning, and separated learning/execution planes. CLAUDE PLAN

I would **not** simply reply `defaults OK`, though. Phase 0 found several issues that should be converted into explicit design decisions before Phase 1.

## My review of Gate 0

### 1. Cloud environment: accept

The measured environment is a good place to run v0.1: Ubuntu 24.04, 4 vCPU, ~16 GB RAM, Python 3.11, inside a Firecracker VM. The important condition is that this exact execution environment must be fingerprinted and kept stable across the experiment.

The current L3 approach is reasonable for this particular benchmark because the generated programs are Python puzzle solutions rather than arbitrary long-lived applications, and the outer Firecracker VM provides an additional isolation boundary. Bubblewrap creates a separate filesystem namespace and can unshare user, PID, network, IPC and other namespaces. [GitHub](https://github.com/containers/bubblewrap/blob/main/bwrap.xml?utm_source=chatgpt.com)

I would **not** require gVisor or VM-per-task for v0.1 unless the actual probes show a problem. That would add substantial complexity before the experiment has demonstrated that the workstation concept is useful.

### 2. Two providers: accept, but fix the benchmark-generation bias

Anthropic + Gemini is reasonable.

Current official documentation shows Gemini 3.8 Flash as a stable model, with introductory pricing through December 31, 2026 of $0.75/M input and $3.75/M output tokens. Anthropic's current model/deprecation documentation lists Claude Haiku 4.5 as active, and Anthropic's published pricing lists $1/M input and $5/M output. [Google AI](https://ai.google.dev/gemini-api/docs/latest-model?hl=en\&utm_source=chatgpt.com)

For the pilot, reasonable concrete candidates are therefore:

`claude-haiku-4-5-20251001`

and

`gemini-3.8-flash`

But these should be treated as **pilot candidates**, not as a preselected "winning" model.

For benchmark generation, I prefer the **50/50 Anthropic/Gemini generation split** over introducing a third provider solely to solve the confound. Every generated task should then be validated cross-family, and the final report should contain a preregistered by-generator-family analysis.

A third family can be added later if an inexpensive, independently accessible one becomes available.

### 3. The biggest experimental problem: the simple baseline is still potentially too weak

This is the most important change I would make.

The workstation can potentially use:

> Anthropic + Gemini + parallel execution + merging + repair + learned routing.

If the strongest simple baseline is restricted to a single model, the workstation could win merely because it has access to a heterogeneous model ensemble.

That would make the result harder to interpret.

I recommend redefining Best-of-N so that it may use a **fixed heterogeneous model pool**, with the model mixture, N, selection rule and repair behavior selected on VALIDATION and then frozen.

That gives you something closer to:

```text
A  Single-shot
B  Fixed best-of-N / heterogeneous sampling
C  Single-model execute-and-repair
D  Workstation-cold
E  Workstation-warm
```

The strongest of A/B/C remains the primary simple baseline.

That is much stronger scientifically.

### 4. H1 wording needs correction

Currently H1 is:

> "Collaboration + verification helps"

But H1 is actually comparing the *whole warm workstation* against the strongest simple baseline.

That does **not** isolate collaboration or verification.

A cleaner formulation is:

> **H1: The adaptive workstation improves verified task outcomes over the strongest simple non-learning baseline.**

Then S1–S5 answer the secondary question of whether increasing collaboration / merge / verification / repair complexity actually contributes anything.

That matches the experimental structure much better.

### 5. The evaluator must be more isolated than "a separate process"

This is a genuine security/integrity issue.

Your packet correctly identifies that a separate process under the same root/UID does not protect the held-out benchmark. PLAN

I want the eventual architecture closer to:

```text
                 CONTROL PLANE
                      │
               Evaluator supervisor
                      │
             ┌────────▼────────┐
             │    EVALUATOR    │
             │ separate UID /  │
             │ stronger sandbox│
             │                 │
             │ hidden tests   │
             │ private key    │
             └────────┬────────┘
                      │
                pass / fail only
                      │
        ┌─────────────▼─────────────┐
        │       LEARNING PLANE      │
        │ orchestrator / strategies │
        │ memory / experiments      │
        └───────────────────────────┘
```

The learning plane should be able to submit code to the evaluator.

It should **not** be able to:

- read the encrypted benchmark
- obtain the decryption key
- inspect evaluator memory
- inspect evaluator environment variables
- inspect decrypted temporary files
- read the held-out result database
- ask the evaluator for hidden failure details

For HELD-OUT specifically, the evaluator should return only the permitted result.

The current Firecracker environment gives you a useful outer boundary, but Firecracker itself recommends dedicated unprivileged identities and defense-in-depth rather than treating a single process as the security boundary. [GitHub](https://github.com/firecracker-microvm/firecracker/blob/main/docs/prod-host-setup.md?utm_source=chatgpt.com)

### 6. Claude Code itself must not be treated as the security boundary

This is worth making explicit.

Claude Code's own documentation describes `bypassPermissions` as giving Claude full system access; permission rules therefore aren't equivalent to an OS security boundary. [Claude Code](https://code.claude.com/docs/zh-CN/agent-sdk/permissions?utm_source=chatgpt.com)

So:

```text
Claude Code permissions
        ≠
workstation security
```

They are development controls.

The real experiment security must come from:

```text
OS / namespace / UID / filesystem / evaluator isolation
```

The reviewer is right that `allowUnsandboxedCommands=false` and `failIfUnavailable=true` should be enforced. Do that.

### 7. The spend guard needs one more layer

The current problem where:

```text
MAX_RUN_COST_USD=999
```

could be supplied by the actor is serious. The gate packet identifies it. PLAN

Use a hierarchy:

```text
GLOBAL_EXPERIMENT_BUDGET
        ↓
EXPERIMENT_BUDGET
        ↓
TASK_BUDGET
        ↓
CALL_BUDGET
```

The environment may **lower** a configured limit, never raise it.

Also make the cumulative ledger persistent and atomic.

For concurrent calls, reserve the maximum predicted cost before making the call, then settle the actual cost afterward. Otherwise two simultaneous workers can each see "$4 remaining" and both spend it.

This is much more important than a prettier cost report.

### 8. Do not use the PILOT tasks as the drift sentinel

The gate packet caught a real specification conflict:

> PILOT is supposed to be never reused, but A2 reuses PILOT tasks. PLAN

I would create a tiny separate:

```text
CONTROL / SENTINEL
```

set, perhaps 15–20 tasks.

It is:

- never used for learning
- never part of the reported benchmark
- never used for strategy promotion
- run before/after experiment sessions

That resolves the conflict cleanly.

Also, **output-hash drift should not be treated as strong evidence of provider drift** when sampling is stochastic. Different outputs are expected. Use performance/pass-rate drift plus provider metadata as the meaningful signal; response hashes can remain telemetry.

### 9. Interleave arms during HELD-OUT

This is missing from the current experimental design and I consider it important.

Do not do:

```text
300 × A
300 × B
300 × C
300 × D
300 × E
```

because provider/environment drift, network congestion, quota changes, or infrastructure changes could correlate with arm.

Instead, for each task:

```text
Task 017
  → random permutation of A/B/C/D/E
```

using a preregistered seed.

The order should be balanced across the benchmark.

That gives you much better protection against time-dependent confounding.

### 10. Generalize the sampling configuration

`PLAN.md` currently speaks in terms of fixed temperatures. PLAN

That should become something like:

```text
sampling_config:
    temperature: ...
    top_p: ...
    thinking_level: ...
    max_output_tokens: ...
    provider_specific_parameters: ...
```

with only parameters actually supported by each model.

This matters because current Anthropic documentation says temperature/top-p/top-k handling differs across current Claude versions, including deprecations on newer models. [Claude Platform Docs](https://docs.anthropic.com/en/docs/about-claude/model-deprecations?utm_source=chatgpt.com)

The experiment should record:

```text
requested parameters
effective parameters
provider response metadata
```

rather than assuming every provider exposes identical controls.

### 11. Memory security should be attacked harder later

The memory design is good, but recent 2026 research gives us another reason not to equate provenance with truth.

MemSecBench reports persistent-memory attacks surviving across later sessions, while another recent work specifically examines "laundering" attacks where summarization, trusted-tool echoes, or manufactured corroboration can make poisoned information appear more trustworthy. [arXiv](https://arxiv.org/abs/2607.27080?utm_source=chatgpt.com)

So at the memory phase I would explicitly test:

```text
direct poisoning
       ↓
summarization laundering
       ↓
false corroboration
       ↓
trusted-tool echo
       ↓
dormant trigger
       ↓
retrieval
       ↓
behavior change
```

The important architectural rule remains:

> **No memory item ever becomes an authority.**

Your existing `MODEL ≠ AUTHORITY` rule protects you even if memory trust scoring is fooled. CLAUDE

---

# My recommended decisions for Claude's 10 questions

| Question | My recommendation |
|---|---|
| Q1 | **Accept** cloud environment, with environment fingerprinting/version lock |
| Q2 | **Accept** Anthropic + Gemini; use cheap stable candidates; 50/50 benchmark generation if no third family |
| Q3 | **Accept provisionally** `$5` invocation cap + `$150` global ceiling, but enforce hierarchical immutable caps and recalculate at Gate 3 |
| Q4 | **Accept** ~30-task human spot-check, ~1 hour at Gate 2 |
| Q5 | **Accept** Python-only |
| Q6 | **Resolved** — the ChatGPT handoff is already present in the material you supplied; no additional file is necessary |
| Q7 | **Accept only with stronger evaluator isolation**; encrypted git is transport/storage, not the security boundary |
| Q8 | **Accept** setup/bootstrap script, but it must fail closed and verify sandbox availability |
| Q9 | **Accept** rename to `env.example` and deny `.env*` broadly |
| Q10 | **Accept** CODEOWNERS + branch protection now, plus filesystem protection of control/safety files |

The provider choice should remain an experimental configuration rather than a claim about model quality. The current APIs already illustrate why exact recording matters: Gemini distinguishes stable/latest/preview model naming, while Anthropic maintains explicit model identifiers and retirement schedules. [Google AI](https://ai.google.dev/gemini-api/docs/models?utm_source=chatgpt.com)

## Message I would relay to Claude Code

I reviewed GATE-0, CLAUDE.md, PLAN.md, and the Claude-chat handoff, and I also checked the current provider/Claude Code documentation.

Do not start Phase 1 yet. Treat this as the external review response for Gate 0.

My recommended decisions:

1. Q1 — ACCEPT the measured cloud environment as the v0.1 experiment environment.

Add an environment fingerprint that records enough information to detect changes between phases/runs: OS/kernel, CPU quota, RAM quota, Python version, SQLite version, sandbox version, and relevant package/runtime versions. The final experiment must abort rather than silently continue under a materially different environment.

2. Q2 — ACCEPT Anthropic + Gemini as the two solver providers.

Use cheap stable models as pilot candidates. Current reasonable candidates are Claude Haiku 4.5 and Gemini 3.8 Flash, but do not treat either as a presumed winner.

Do NOT make a third provider a hard requirement merely to solve generator bias.

Instead, unless a cheap independent third family is easily available, generate the benchmark 50/50 across Anthropic and Gemini, validate each task cross-family, and preregister a by-generator-family analysis.

3. Q3 — ACCEPT $5 as the provisional invocation ceiling and $150 as the provisional total experiment ceiling, but fix the budget model before paid experiments.

The budget must have a hierarchy:

GLOBAL EXPERIMENT CAP
→ EXPERIMENT CAP
→ TASK CAP
→ CALL CAP

The learning plane must not be able to raise these values through environment variables.

Environment variables may only reduce configured caps.

Maintain a persistent cumulative ledger across process restarts.

For concurrency, reserve the maximum predicted call cost before the API call, then settle/release the difference after the real usage is known.

Gate 3 must recalculate the total projected cost from real pilot usage before the held-out experiment is approved.

4. Q4 — ACCEPT ~30 human spot-checked tasks and ~1 hour at Gate 2.

5. Q5 — ACCEPT Python-only tasks for v0.1.

Keep the execution environment deterministic and explicitly versioned.

6. Q6 — RESOLVED.

The ChatGPT handoff is already included in the external material that Ridha supplied. No additional handoff file is necessary.

7. Q7 — DO NOT treat "encrypted in git + separate evaluator process" as the final security boundary.

Encryption is acceptable for storage/transport, but the final architecture must ensure the learning plane cannot obtain the decryption key or decrypted held-out data.

Design toward:

LEARNING PLANE
→ evaluator request interface
→ separate evaluator identity/sandbox
→ pass/fail result only

The learning plane must not be able to read:

- the encryption key
- hidden tests
- decrypted benchmark files
- evaluator environment variables
- evaluator process memory
- decrypted temporary files
- held-out result storage

For v0.1, use the existing Firecracker environment as the outer isolation boundary and add separate UID/process/filesystem isolation inside it. Do not require VM-per-task unless testing shows that the current boundary is insufficient.

8. Q8 — ACCEPT.

Add the bootstrap/setup script, but make it fail closed.

If bwrap or another required security component is unavailable, the workstation must not silently downgrade to a weaker execution mode.

Record the exact installed versions and run capability probes after setup.

9. Q9 — ACCEPT.

Rename `.env.example` to `env.example`.

Treat `.env*` as protected at all depths. Also ensure the development sandbox does not expose provider credentials through inherited environment variables.

10. Q10 — ACCEPT.

Add CODEOWNERS and branch protection now.

Also make the following files/directories builder-unwritable through the development sandbox:

- security configuration
- policy configuration
- evaluator code/config
- benchmark protection configuration
- CI security configuration
- safety tests

Do not confuse GitHub governance with runtime security. The final experiment must execute from a frozen commit/configuration snapshot that the learning plane cannot modify.

Additional required amendments:

A8 — H1 wording.

Change H1 from:

"Collaboration + verification helps"

to:

"The adaptive workstation improves verified task outcomes over the strongest simple non-learning baseline."

Do not claim that this comparison isolates collaboration or verification.

Use the S1–S5 strategy ladder to study those design choices separately.

A9 — Strengthen the simple baseline.

The workstation can use multiple heterogeneous providers. Therefore Best-of-N must be allowed to use a fixed heterogeneous model pool, not only repeated samples from one model.

Model mixture, N, selection procedure and any fixed routing must be selected on VALIDATION and frozen before HELD-OUT.

The strongest of A/B/C remains the primary simple baseline.

Otherwise the workstation could appear superior merely because it can call multiple model families while the baseline cannot.

A10 — Strengthen evaluator/learning separation.

The evaluator must receive submissions without exposing its hidden benchmark to the learning plane.

For HELD-OUT, the evaluator must return only the minimum permitted result.

Do not route held-out results through the ordinary learning/memory pipeline.

A11 — Fix arm-order and provider-drift confounding.

For each HELD-OUT task, execute arms A–E in a preregistered pseudorandom balanced order instead of running all tasks for one arm and then all tasks for another.

Record exact timestamps and provider metadata.

Create a separate 15–20 task CONTROL/SENTINEL set. Do not reuse PILOT tasks, because PLAN.md says PILOT is never reused.

Use pass-rate/control-task behavior and provider metadata as the primary drift signal. Do not treat ordinary stochastic output-hash changes as proof of provider drift.

A12 — Generalize sampling configuration.

Do not assume every provider supports the same sampling controls.

Record requested and effective generation parameters per provider/model, including whatever the model actually supports.

Do not hard-code a universal dependency on temperature.

Phase 2 security requirements:

- L3 only for model-generated code execution
- fail closed if L3 is unavailable
- add AF_UNIX escape tests
- add setns/network-namespace escape tests
- add per-run process/resource isolation
- remove the shared-UID fork limitation
- ensure executor processes are non-root
- verify the child environment is explicitly constructed

Phase 6 memory requirements:

Add adversarial tests for:

- direct memory poisoning
- summarization laundering
- false corroboration
- trusted-tool echo
- dormant/context-triggered poisoning
- duplicate-source Sybil attacks
- quarantine flooding

Provenance must remain evidence metadata, never authority.

Finally, update docs/DECISIONS.md with these amendments before Phase 1 begins.

The Gate 0 result is therefore:

APPROVE THE DIRECTION, BUT KEEP THE PROJECT AT THE GATE UNTIL THESE DECISIONS/AMENDMENTS ARE RECORDED.

Do not build Phase 1+ code until the Gate 0 state reflects them.

The experiment should remain deliberately capable of producing a null result. Do not optimize the architecture for making the workstation win.

### One especially important point

Claude's current report says the development sandbox is already active, while also explicitly documenting that it **does not protect against a determined builder**. That distinction should remain visible. The project should never depend on Claude Code "being good" for the validity of the experiment. PLAN

The strongest conceptual version of this workstation is:

```text
             AI MODELS
                 │
                 ▼
        ┌─────────────────┐
        │   WORKSTATION   │
        │                 │
        │ strategies      │
        │ routing         │
        │ memory          │
        │ collaboration   │
        │ learning        │
        └────────┬────────┘
                 │
        requests / submissions
                 │
                 ▼
        ┌─────────────────┐
        │  HARD CONTROL   │
        │                 │
        │ policy          │
        │ sandbox         │
        │ evaluator       │
        │ budget          │
        └────────┬────────┘
                 │
                 ▼
           MEASURED RESULT
                 │
                 ▼
        experience / learning
```

That separation is more important than adding more agents, more memory, MCP, vector databases, or unrestricted strategy evolution. Your `PLAN.md` already has the right instinct: v0.1 exists to determine whether continual adaptation produces measurable gains, not to build the most elaborate agent framework possible. PLAN

I also surfaced a GitHub connection option so I can inspect the repository/branches directly in future review cycles; connect it only if you want that deeper repo-level review.
