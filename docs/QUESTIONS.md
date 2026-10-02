# Open questions for Ridha

Each question gives why it matters and a **recommended default**. Answered questions move to the bottom.

---

### Q15. Which free providers? *(new)*
**Why:** $0 budget (D-021). Cross-checking with a second model family is a core idea; today only Gemini works.
**Default:** Gemini (have) + one of Groq / OpenRouter `:free` / GitHub Models / Mistral free tier (free tiers change; verify at sign-up). For each: key as an environment variable, and its host allowed in Network access.

### Q16. Local models: where? *(new)*
**Why:** this cloud container has no GPU (4 CPU, 16 GB), so only tiny models run here, slowly. Running on your PC changes the sandbox design (Windows → WSL2).
**Default:** cloud + free APIs first; local later. Tell me your PC's OS, RAM, GPU.

### Q17. "OpenCode": the agent app or its models? *(new)*
**Default:** agent apps stay deferred (D-017). If its free models have a plain API, I use that. Strong models (Opus etc.) wait until after v0.1 (they need a paid API).

### Q18. Coding first? *(new)*
**Default: yes.** Python tasks with tests give automatic, trustworthy scoring. Reasoning/math later.

### Q19. Time budget? *(new)*
**Why:** free tiers limit requests per day, so time is the real budget.
**Default:** runs may take hours or days, spread over sessions. I build resumable runs.

---

## Answered

| # | Answer (2026-10-02) |
|---|---|
| Q1 | Cloud environment, with environment fingerprinting (R1) |
| Q2 | Anthropic + Gemini, 50/50 generation, cross-family validation; pilot candidates `claude-haiku-4-5-20251001`, `gemini-3.8-flash` (refined by Q12) |
| Q3 | `MAX_RUN_COST_USD=5`, $150 provisional; hierarchical caps, env may only lower; re-estimate at the pilot (likely ~$170–230 for the full design) |
| Q4 | Yes, ~30 tasks, ~1 h |
| Q5 | Python only |
| Q6 | ChatGPT handoff received (D-001) |
| Q7 | Encrypted storage + separate evaluator identity; encryption is not the boundary (A10) |
| Q8 | Yes, fail-closed setup script. **Your action:** see `docs/NEXT_SESSION.md` |
| Q9 | Done: `env.example`, `.env*` denied everywhere |
| Q10 | Done: CODEOWNERS + write-protected safety files. **Your action:** branch protection (see `docs/NEXT_SESSION.md`); strict sandbox after Q8 |
| Q11 | Yes: Q1–Q10 + A8–A12 adopted (A9 as modified by the builder) |
| Q12 | Yes: Gemini (AI Studio key) first; Anthropic optional (no key yet); shadow-cost budgets (D-016); no chat apps, no agent CLIs (D-017) |
| Q13 | Yes: milestones M1→M4 (D-018). M1–M3 results are exploratory |
| Q14 | Default (b): keep today's sandbox mode until the executor exists, then pick (a) or (c) |
| — | No paid API keys, ever: $0 real budget, free/local models only (D-021) |
| — | Claude (chat) review: skipped for Gate 0; ChatGPT only |
