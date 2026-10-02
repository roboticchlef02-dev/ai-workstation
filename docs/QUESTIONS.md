# Open questions for Ridha

Each question gives why it matters and a **recommended default**. Answered questions move to the bottom.

---

### Q14. Strict dev sandbox: when and how? *(new)*
**Why:** you approved strict mode. But nested bwrap hangs inside the dev sandbox, so strict mode would stop me from running the executor's security tests, the L3 probe and live API calls (D-019).
**Default: (b)** keep today's mode until the executor exists, then pick (a) or (c):
- (a) strict + an exception for git and one fixed executor-test command
- (c) strict; executor tests run only in CI

The settings file is write-protected and the auto-mode classifier blocks me from changing my own sandbox, so **you** apply the change when you choose. I'll give you the exact JSON.

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
| — | Claude (chat) review: skipped for Gate 0; ChatGPT only |
