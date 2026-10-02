# Open questions for Ridha

Each question gives why it matters and a **recommended default**. Reply "defaults OK" or override by number.
Answered questions move to the bottom with the answer and date. I won't ask again unless new evidence invalidates an answer.

---

### Q1. Where will the experiment run? *(PLAN §10 Q1)*
**Why:** the machine decides the sandbox. I measured this cloud environment (Linux, 4 vCPU, 16 GB, isolation level L3 shown). I have not measured your PC. Native Windows has no Claude Code sandbox, and a weak PC can't run containers comfortably.
**Default: A, this Claude Code cloud environment.**
- A: cloud. Strongest isolation available. Needs Q7 and Q8 because the container is wiped when idle.
- B: your PC. Tell me OS, RAM, CPU. I'll then run `python scripts/detect_env.py` there and re-plan the sandbox.

### Q2. Which two providers and models? Are the keys set? Do they have provider-side spend limits? *(PLAN §10 Q2)*
**Why:** two model families are needed for the collaboration arms and to separate generator bias from solver ability.
**Found:** no provider key variables are set in this environment (I checked names only, never values). Network policy here allows Anthropic and Google Gemini. **OpenAI and DeepSeek are blocked** unless you add `api.openai.com` / `api.deepseek.com` to the environment's allowed domains.
**Default:** Anthropic plus one of {Gemini, OpenAI}, using a *cheap-tier* model from each as solvers (e.g. Claude Haiku 4.5 plus the other provider's cheapest current model). I'll confirm exact model IDs at Phase 1 from each provider's free model-list endpoint. Generator = provider X, independent validator = provider Y.
**How to give keys:** add them as environment variables in this cloud environment's settings (environment menu in the session title bar → Edit), named `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` or `OPENAI_API_KEY`. They apply to a **new** session. Never paste keys in chat. Also set a monthly spend limit in each provider's console.
**Note:** the $100 Claude credit you mentioned covers Claude app/Claude Code usage. It is **not** API credit. API calls are billed separately by each provider.

### Q3. Total experiment budget and `MAX_RUN_COST_USD`? *(PLAN §10 Q3)*
**Why:** sets pool sizes, model tier and whether repeats are affordable.
**Rough estimate before any pilot (low confidence; Gate 3 replaces it with measured numbers):** about 29k model calls across generation, pilot, train, validation (strategy ladder, A/B, learning curve, 2×2) and held-out × 5 arms, which comes to **~$100 with cheap-tier models, ~$650 with mid-tier**, excluding repeats.
**Default:** `MAX_RUN_COST_USD = 5`, total hard ceiling **$150** with cheap-tier models, revisited at Gate 3 with pilot data. Nothing paid runs before Gate 3 except benchmark generation at Gate 2, which gets its own estimate and your approval first.

### Q4. Can you spot-check ~30 generated tasks, and how much time per gate? *(PLAN §10 Q4)*
**Why:** the human spot-check is the only non-model check of task clarity and correctness.
**Default:** yes, about 1 hour at Gate 2 (I'll prepare a one-page-per-task review sheet). 15–30 min at the other gates.

### Q5. Python-only tasks to start? *(PLAN §10 Q5)*
**Why:** one language keeps the sandbox, evaluator and test generation simple.
**Default:** yes, Python only.

### Q6. ChatGPT's handoff was not included. *(new)*
**Why:** the prompt says to read it. Only `CLAUDE.md`, `PLAN.md` and Claude's handoff arrived.
**Default:** send it if it exists. Until then I proceed without it; Phase 0 does not depend on it.

### Q7. Where do held-out tasks and experiment state live? *(new, only matters if Q1 = A)*
**Why:** the cloud container is wiped when idle, so anything not in git is lost. But held-out tasks in plaintext git can be read by any future session (`git show` bypasses path deny rules). That breaks "held-out never opened during development".
**Options:**
- (a) Held-out committed **encrypted**, with the key in an env var that only the evaluator process reads and the dev sandbox unsets.
- (b) Held-out stored off-repo (e.g. your machine or private storage) and loaded only for the final run.
- (c) Plaintext in git, protected by deny rules only. Weakest.

**Default: (a).** Decide before Gate 2. Experiment results (SQLite) are committed per phase or exported as a report (decide at Phase 1).

### Q8. Add a setup script to the cloud environment? *(new, only if Q1 = A)*
**Why:** I installed `bubblewrap` and `socat` by hand in this session. A fresh container won't have them, so the executor would drop to L2 and Claude Code's dev sandbox would silently run unsandboxed. Also, `pip install` can't run from inside the dev sandbox.
**Default: yes.** Add these lines to the environment's setup script:
```
apt-get update && apt-get install -y bubblewrap socat
pip install pydantic httpx pyyaml pytest
```
Once that's in place I'll also set `sandbox.failIfUnavailable: true` so a missing sandbox stops the session instead of degrading silently.

---

## Answered
(none yet)
