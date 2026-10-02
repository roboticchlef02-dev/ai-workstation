# Open questions for Ridha

Each question gives why it matters and a **recommended default**. Answered questions move to the bottom.

---

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
| Q15 | Any free provider → builder picks OpenCode Zen (one key, several free model families) + Gemini (D-023) |
| Q16 | Yes: the workstation and local models will run on Ridha's PC |
| Q17 | OpenCode = its model gateway (Big Pickle, MiniMax, …), used through its API, not the agent app |
| Q18 | Yes: Python coding first |
| Q19 | Yes: long, resumable runs are fine |
| — | New requirement: learned knowledge must carry over when the model changes, at low token cost (D-022) |
| Q20 | PC: i5 8th gen, 8 GB RAM, no GPU, 256 GB SSD; may change later. Local models: only small ones, slowly. Free cloud APIs are the main path; development stays in the cloud |
| Q21 | Yes: learned knowledge stored as Markdown files, the armor pack (D-024) |
| — | Groq and OpenRouter keys added (observed set; hidden in sandboxed commands). Hosts still blocked by Network access |
| — | Claude (chat) review: skipped for Gate 0; ChatGPT only |
