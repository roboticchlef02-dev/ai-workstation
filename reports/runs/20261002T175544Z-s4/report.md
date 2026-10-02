# Run 20261002T175544Z-s4

> **Exploratory (M1).** Builder-written seed tasks, one run, no confidence intervals. This shows the loop works; it is not evidence for H1/H2 (D-018).

- Models: groq/qwen/qwen3.8-27b, groq/openai/gpt-oss-20b
- Tasks: 10 from `benchmarks/seed` (sha256 2d679503cc90…), pool SEED
- Arms: A1, C1, A2, C2, D · repair rounds {'A': 0, 'C': 3, 'D': 2} · max output tokens 8192
- Sandbox L3 · evaluator 0.2.0 · templates m1-v1 · seed 4
- Compared on the **10 tasks** that every arm finished.

## Results

| Arm | Solved | Pass rate | Hidden tests passed | Model calls | Calls/task | Input tok | Output tok | Shadow $ | Infra issues* |
|---|---|---|---|---|---|---|---|---|---|
| A1 single shot (qwen3.8-27b) | 9/10 | 90% | 78/83 (94%) | 10 | 1.0 | 2578 | 4073 | 0.0043 | 0 |
| C1 execute + repair (qwen3.8-27b) | 10/10 | 100% | 83/83 (100%) | 10 | 1.0 | 2578 | 4129 | 0.0043 | 0 |
| A2 single shot (gpt-oss-20b) | 9/10 | 90% | 82/83 (99%) | 10 | 1.0 | 3062 | 6840 | 0.0037 | 0 |
| C2 execute + repair (gpt-oss-20b) | 9/10 | 90% | 82/83 (99%) | 10 | 1.0 | 3062 | 9883 | 0.0053 | 0 |
| D two-model workstation (qwen3.8-27b + gpt-oss-20b) | 9/10 | 90% | 82/83 (99%) | 20 | 2.0 | 5640 | 11051 | 0.0083 | 0 |

Hidden tests passed: partial credit, summed over tasks (a task counts as solved only if all its hidden tests pass).

\* Infra issues: provider calls that failed after retries, budget stops and evaluator errors. Each one also counts as a fail in this table.
Model calls exclude retried rate-limit errors. Wall time (in results.jsonl) includes free-tier pacing and retry waits.

**D vs the best single-model arm (C1):** 90% vs 100% (-10%). One exploratory run: not a significant result either way.

## By category (solved / tasks)

| Category | A1 | C1 | A2 | C2 | D |
|---|---|---|---|---|---|
| arrays | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| data_structures | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| dynamic_programming | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| graphs | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| greedy | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| hash_maps | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| numerical | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| strings | 1/2 | 2/2 | 1/2 | 1/2 | 1/2 |

## Per task

| Task | Difficulty | A1 | C1 | A2 | C2 | D |
|---|---|---|---|---|---|---|
| seed-arr-04 | 3 | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-dp-04 | 4 | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-ds-03 | 4 | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-graph-04 | 3 | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-greedy-03 | 4 | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-hash-04 | 4 | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-num-04 | 3 | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-num-05 | 3 | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-str-04 | 4 | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-str-05 | 4 | ❌ (1) | ✅ (1) | ❌ (1) | ❌ (1) | ❌ (2) |

Cells: hidden-test verdict (model calls used).
