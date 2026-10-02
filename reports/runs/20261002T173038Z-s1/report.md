# Run 20261002T173038Z-s1

> **Exploratory (M1).** Builder-written seed tasks, one run, no confidence intervals. This shows the loop works; it is not evidence for H1/H2 (D-018).

- Models: gemini/gemma-4-26b-a4b-it, gemini/gemma-4-31b-it
- Tasks: 9 from `benchmarks/seed` (sha256 be335867fe4f…), pool SEED
- Arms: A, C, D · repair rounds {'A': 0, 'C': 3, 'D': 2} · max output tokens 8192
- Sandbox L3 · evaluator 0.1.0 · templates m1-v1 · seed 1
- Compared on the **3 tasks** that every arm finished.
- **Stopped early:** only 3 of 9 tasks ran

## Results

| Arm | Solved | Pass rate | Hidden tests passed | Model calls | Calls/task | Input tok | Output tok | Shadow $ | Infra issues* |
|---|---|---|---|---|---|---|---|---|---|
| A single shot (gemma-4-26b-a4b-it) | 3/3 | 100% | 16/16 (100%) | 3 | 1.0 | 752 | 9664 | 0.0000 | 0 |
| C execute + repair (gemma-4-26b-a4b-it) | 3/3 | 100% | 16/16 (100%) | 3 | 1.0 | 752 | 6470 | 0.0000 | 0 |
| D two-model workstation (gemma-4-26b-a4b-it + gemma-4-31b-it) | 3/3 | 100% | 16/16 (100%) | 6 | 2.0 | 1504 | 12291 | 0.0000 | 0 |

Hidden tests passed: partial credit, summed over tasks (a task counts as solved only if all its hidden tests pass).

\* Infra issues: provider calls that failed after retries, budget stops and evaluator errors. Each one also counts as a fail in this table.
Model calls exclude retried rate-limit errors. Wall time (in results.jsonl) includes free-tier pacing and retry waits.

**D vs the best single-model arm (A):** 100% vs 100% (+0%). One exploratory run: not a significant result either way.

## By category (solved / tasks)

| Category | A | C | D |
|---|---|---|---|
| data_structures | 1/1 | 1/1 | 1/1 |
| dynamic_programming | 1/1 | 1/1 | 1/1 |
| graphs | 1/1 | 1/1 | 1/1 |

## Per task

| Task | Difficulty | A | C | D |
|---|---|---|---|---|
| seed-dp-03 | 3 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-ds-01 | 3 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-graph-03 | 3 | ✅ (1) | ✅ (1) | ✅ (2) |

Cells: hidden-test verdict (model calls used).
