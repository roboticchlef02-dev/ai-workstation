# AI Workstation v0.1

An environment that wraps free (or any) AI models with verification, repair, collaboration and, later, learned knowledge stored as Markdown ("the armor pack", D-024), to measure whether weak models get better results without changing their weights. A null result is a valid outcome.

- Rules: [`CLAUDE.md`](CLAUDE.md) · Plan: [`PLAN.md`](PLAN.md) · Decisions: [`docs/DECISIONS.md`](docs/DECISIONS.md) · Open questions: [`docs/QUESTIONS.md`](docs/QUESTIONS.md)
- Gate packets: [`docs/gates/`](docs/gates/) · Environment: [`docs/ENVIRONMENT.md`](docs/ENVIRONMENT.md) · Run reports: [`reports/runs/`](reports/runs/)

**Status:** M1 (working loop). Exploratory results only (D-018).

## How it works (M1)
1. A **task** (statement + visible examples) goes to one or two models.
2. Their code runs in an **L3 sandbox** (bwrap + unprivileged uid, no network, host hidden).
3. Arms: **A** single shot · **C** execute visible examples and repair · **D** two models, pick a passing answer, cross-model repair.
4. A separate **evaluator** process scores the final code on **hidden** tests.
5. A Markdown **report** compares the arms (pass rate, calls, tokens, cost).

## Run
Needs Linux, root (for the sandbox's privilege drop), bubblewrap and util-linux `setpriv`.

```bash
pip install -e ".[dev]"
pytest -m "not live"                                   # sandbox tests need root + bwrap
python scripts/detect_env.py                           # host + isolation probe (expect L3)
python -m aiws.run --models gemini:gemma-4-26b-a4b-it,gemini:gemma-4-31b-it \
                   --arms A,C,D --limit 5 --confirm-spend
```

Model specs: `gemini:<model>`, `groq:<model>`, `openrouter:<model>`, `opencode:<model>`, `local:<model>[@url]`. Keys come from environment variables (`GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `OPENCODE_API_KEY`); see `env.example`. Every model needs an entry in `configs/prices.yaml` (unknown models are refused).
