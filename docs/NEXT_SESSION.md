# Next session — start here

**State (2026-10-02):** Gate 0 closed. No Phase 1 / M1 code yet. Branch `claude/dazzling-albattani-l57sv4`, CI green before the last commits.

## Ridha: do these before the next session (≈5 min)
1. **Setup script** (cloud environment menu in the session title bar → Edit → Setup script):
   ```bash
   set -e
   apt-get update && apt-get install -y bubblewrap socat
   pip install "pydantic>=2.6" "httpx>=0.27" "pyyaml>=6.0" "pytest>=8.0"
   bwrap --version
   ```
2. **Keys** (same Edit screen → environment variables): `GEMINI_API_KEY` and/or `ANTHROPIC_API_KEY`. Never in chat.
3. **Optional: protect `main`.** Only the working branch exists today. On GitHub, create `main` from this branch and make it the default. Then Settings → Rules → New branch ruleset for `main`:
   - require a pull request
   - require status check `ci`
   - block force pushes

   A solo account can't approve its own PRs. Add yourself to the bypass list so only *you* merge.
4. Answer **Q12** (which keys/accounts) and **Q13** (milestones) in `docs/QUESTIONS.md`. You can just say "Q12: <keys>, Q13 yes".

## Prompt to paste into the new session
> Read CLAUDE.md, docs/NEXT_SESSION.md, docs/QUESTIONS.md and the latest part of docs/DECISIONS.md. Gate 0 is closed. My answers: Q12 = …, Q13 = …. Verify the setup script worked (`python scripts/detect_env.py`; expect L3) and keys are present (names only). Then start the next step. Stop when the conversation gets long, and update docs/NEXT_SESSION.md before stopping.

## Builder checklist for the next session
- Verify `bwrap`, pytest, and the L3 probe. If they're OK, enable the strict sandbox (`allowUnsandboxedCommands:false`, `failIfUnavailable:true`, exclude only `git commit`/`git push`), per Q10 and R6.
- If Q13 = yes, start **M1** with security tests first: secrets never logged; budget caps + reserve/settle + shadow cost (D-016); executor L3-only, non-root, AF_UNIX/setns escape tests; clean child env.
- Keep each session's work small and committed. Update this file at the end.
