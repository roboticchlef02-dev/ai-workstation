# Open questions for Ridha

Each question gives why it matters and a **recommended default**. Answered questions move to the bottom.

---

### Q12. Which free / subscription models exactly? *(new)*
**Why:** you said you may use free or subscription models. That changes how cost is counted (D-016) and which access types are safe (D-017).
**Default:**
- A **Gemini API key from Google AI Studio** (free tier) as the first real provider.
- Optionally an **Anthropic API key** (Haiku 4.5 is ~$0.007 per call). There is no free Anthropic API tier.
- Budgets counted in list-price "shadow dollars", so free calls still count.
- Subscription chat apps can't be used. Agent CLIs are deferred.

Tell me which accounts/keys you have. Add keys as environment variables in the cloud environment settings, never in chat. A **new session** picks them up.

### Q13. Switch to small working milestones (M1→M4)? *(new, budget-tight)*
**Why:** you want something that works soon and improves a little each time. The current plan only gives a result at phase 10.
**Default: yes.** **M1** = one end-to-end working loop:
- real models (free tier is fine) solve ~40 tasks
- code runs in the sandbox, the evaluator scores it
- 3 arms (single shot, repair, simple 2-model workstation)
- a cost/accuracy report

Then M2 learning, M3 memory, M4 the full rigorous experiment. Results before M4 are labeled exploratory, so validity isn't compromised. Details: D-018.

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
| — | Claude (chat) review: skipped for Gate 0; ChatGPT only |
