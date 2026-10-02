# Run 20261002T173703Z-s2

> **Exploratory (M1).** Builder-written seed tasks, one run, no confidence intervals. This shows the loop works; it is not evidence for H1/H2 (D-018).

- Models: groq/qwen/qwen3.8-27b, groq/openai/gpt-oss-20b
- Tasks: 27 from `benchmarks/seed` (sha256 be335867fe4f…), pool SEED
- Arms: A, C, D · repair rounds {'A': 0, 'C': 3, 'D': 2} · max output tokens 8192
- Sandbox L3 · evaluator 0.1.0 · templates m1-v1 · seed 2
- Compared on the **27 tasks** that every arm finished.

## Results

| Arm | Solved | Pass rate | Hidden tests passed | Model calls | Calls/task | Input tok | Output tok | Shadow $ | Infra issues* |
|---|---|---|---|---|---|---|---|---|---|
| A single shot (qwen3.8-27b) | 27/27 | 100% | 166/166 (100%) | 27 | 1.0 | 5700 | 5375 | 0.0066 | 0 |
| C execute + repair (qwen3.8-27b) | 27/27 | 100% | 166/166 (100%) | 27 | 1.0 | 5700 | 5487 | 0.0067 | 0 |
| D two-model workstation (qwen3.8-27b + gpt-oss-20b) | 27/27 | 100% | 166/166 (100%) | 54 | 2.0 | 12683 | 16188 | 0.0128 | 0 |

Hidden tests passed: partial credit, summed over tasks (a task counts as solved only if all its hidden tests pass).

\* Infra issues: provider calls that failed after retries, budget stops and evaluator errors. Each one also counts as a fail in this table.
Model calls exclude retried rate-limit errors. Wall time (in results.jsonl) includes free-tier pacing and retry waits.

**D vs the best single-model arm (A):** 100% vs 100% (+0%). One exploratory run: not a significant result either way.

## By category (solved / tasks)

| Category | A | C | D |
|---|---|---|---|
| arrays | 3/3 | 3/3 | 3/3 |
| data_structures | 2/2 | 2/2 | 2/2 |
| dynamic_programming | 3/3 | 3/3 | 3/3 |
| graphs | 3/3 | 3/3 | 3/3 |
| greedy | 2/2 | 2/2 | 2/2 |
| hash_maps | 3/3 | 3/3 | 3/3 |
| numerical | 3/3 | 3/3 | 3/3 |
| recursion | 2/2 | 2/2 | 2/2 |
| sorting_search | 3/3 | 3/3 | 3/3 |
| strings | 3/3 | 3/3 | 3/3 |

## Per task

| Task | Difficulty | A | C | D |
|---|---|---|---|---|
| seed-arr-01 | 1 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-arr-02 | 1 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-arr-03 | 2 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-dp-01 | 2 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-dp-02 | 2 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-dp-03 | 3 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-ds-01 | 3 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-ds-02 | 2 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-graph-01 | 2 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-graph-02 | 2 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-graph-03 | 3 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-greedy-01 | 2 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-greedy-02 | 2 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-hash-01 | 1 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-hash-02 | 2 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-hash-03 | 2 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-num-01 | 2 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-num-02 | 1 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-num-03 | 3 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-rec-01 | 2 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-rec-02 | 1 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-sort-01 | 2 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-sort-02 | 2 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-sort-03 | 2 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-str-01 | 1 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-str-02 | 1 | ✅ (1) | ✅ (1) | ✅ (2) |
| seed-str-03 | 3 | ✅ (1) | ✅ (1) | ✅ (2) |

Cells: hidden-test verdict (model calls used).
