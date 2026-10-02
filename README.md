# AI Workstation v0.1

An experiment, not a product: does a continual-adaptation layer around existing LLMs (shared memory, verification by tests, collaboration, strategy selection) measurably beat strong simple baselines at matched cost? A null result is a valid outcome.

- Rules: [`CLAUDE.md`](CLAUDE.md) · Plan: [`PLAN.md`](PLAN.md) · Decisions: [`docs/DECISIONS.md`](docs/DECISIONS.md) · Open questions: [`docs/QUESTIONS.md`](docs/QUESTIONS.md)
- Gate packets: [`docs/gates/`](docs/gates/) · Environment: [`docs/ENVIRONMENT.md`](docs/ENVIRONMENT.md)

**Status:** Phase 0 (foundation). No model code, no API calls.

```bash
pip install -e ".[dev]"
pytest -m "not live"
python scripts/detect_env.py   # host + isolation probe
```
