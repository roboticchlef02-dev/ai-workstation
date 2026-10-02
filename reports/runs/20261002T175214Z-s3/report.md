# Run 20261002T175214Z-s3

> **Exploratory (M1).** Builder-written seed tasks, one run, no confidence intervals. This shows the loop works; it is not evidence for H1/H2 (D-018).

- Models: groq/allam-2-7b
- Tasks: 27 from `benchmarks/seed` (sha256 be335867fe4f…), pool SEED
- Arms: A1, C1 · repair rounds {'A': 0, 'C': 3, 'D': 2} · max output tokens 2048
- Sandbox L3 · evaluator 0.2.0 · templates m1-v1 · seed 3
- Compared on the **27 tasks** that every arm finished.

## Results

| Arm | Solved | Pass rate | Hidden tests passed | Model calls | Calls/task | Input tok | Output tok | Shadow $ | Infra issues* |
|---|---|---|---|---|---|---|---|---|---|
| A1 single shot (allam-2-7b) | 2/27 | 7% | 31/166 (19%) | 27 | 1.0 | 6437 | 9062 | 0.0025 | 0 |
| C1 execute + repair (allam-2-7b) | 3/27 | 11% | 53/166 (32%) | 98 | 3.6 | 45252 | 31814 | 0.0109 | 0 |

Hidden tests passed: partial credit, summed over tasks (a task counts as solved only if all its hidden tests pass).

\* Infra issues: provider calls that failed after retries, budget stops and evaluator errors. Each one also counts as a fail in this table.
Model calls exclude retried rate-limit errors. Wall time (in results.jsonl) includes free-tier pacing and retry waits.

## By category (solved / tasks)

| Category | A1 | C1 |
|---|---|---|
| arrays | 0/3 | 0/3 |
| data_structures | 0/2 | 0/2 |
| dynamic_programming | 0/3 | 1/3 |
| graphs | 0/3 | 0/3 |
| greedy | 0/2 | 0/2 |
| hash_maps | 1/3 | 2/3 |
| numerical | 0/3 | 0/3 |
| recursion | 1/2 | 0/2 |
| sorting_search | 0/3 | 0/3 |
| strings | 0/3 | 0/3 |

## Per task

| Task | Difficulty | A1 | C1 |
|---|---|---|---|
| seed-arr-01 | 1 | ❌ (1) | ❌ (4) |
| seed-arr-02 | 1 | ❌ (1) | ❌ (4) |
| seed-arr-03 | 2 | ❌ (1) | ❌ (4) |
| seed-dp-01 | 2 | ❌ (1) | ✅ (1) |
| seed-dp-02 | 2 | ❌ (1) | ❌ (4) |
| seed-dp-03 | 3 | ❌ (1) | ❌ (4) |
| seed-ds-01 | 3 | ❌ (1) | ❌ (4) |
| seed-ds-02 | 2 | ❌ (1) | ❌ (4) |
| seed-graph-01 | 2 | ❌ (1) | ❌ (4) |
| seed-graph-02 | 2 | ❌ (1) | ❌ (4) |
| seed-graph-03 | 3 | ❌ (1) | ❌ (4) |
| seed-greedy-01 | 2 | ❌ (1) | ❌ (4) |
| seed-greedy-02 | 2 | ❌ (1) | ❌ (4) |
| seed-hash-01 | 1 | ✅ (1) | ✅ (1) |
| seed-hash-02 | 2 | ❌ (1) | ✅ (2) |
| seed-hash-03 | 2 | ❌ (1) | ❌ (4) |
| seed-num-01 | 2 | ❌ (1) | ❌ (2) |
| seed-num-02 | 1 | ❌ (1) | ❌ (4) |
| seed-num-03 | 3 | ❌ (1) | ❌ (4) |
| seed-rec-01 | 2 | ❌ (1) | ❌ (4) |
| seed-rec-02 | 1 | ✅ (1) | ❌ (4) |
| seed-sort-01 | 2 | ❌ (1) | ❌ (4) |
| seed-sort-02 | 2 | ❌ (1) | ❌ (4) |
| seed-sort-03 | 2 | ❌ (1) | ❌ (4) |
| seed-str-01 | 1 | ❌ (1) | ❌ (4) |
| seed-str-02 | 1 | ❌ (1) | ❌ (4) |
| seed-str-03 | 3 | ❌ (1) | ❌ (4) |

Cells: hidden-test verdict (model calls used).
