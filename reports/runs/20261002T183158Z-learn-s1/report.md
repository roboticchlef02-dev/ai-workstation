# Learning run 20261002T183158Z-learn-s1

> **Exploratory (M2).** Builder-written seed tasks, one run, small n. EVAL tasks were seen in M1, so this is not a held-out result and not evidence for H2 (D-018, D-027).

- Models: groq/allam-2-7b
- Options: single@1, repair@1, selftest@1 · cold = `repair@1` · TRAIN options per task: 2
- TRAIN 21 tasks · EVAL 16 tasks (split seed 1) · benchmark sha256 2d679503cc90… · evaluator 0.2.0
- Sandbox L3 · templates m2-v1 · seed 1
- EVAL compared on the **16 tasks** every option finished. Warm and cold are scored on the same runs (paired by task).

## EVAL (frozen)

| Policy | Solved | Pass rate | Hidden tests passed | Calls/task | Infra issues |
|---|---|---|---|---|---|
| **warm** (frozen selector) | 1/16 | 6% | 22/110 (20%) | 3.2 | 0 |
| **cold** (repair@1) | 1/16 | 6% | 21/110 (19%) | 3.7 | 0 |
| single@1 | 1/16 | 6% | 25/110 (23%) | 1.0 | 0 |
| repair@1 | 1/16 | 6% | 21/110 (19%) | 3.7 | 0 |
| selftest@1 | 1/16 | 6% | 24/110 (22%) | 3.9 | 0 |

**Warm vs cold:** 1/16 vs 1/16; tasks only warm solved: 0, only cold solved: 0; exact McNemar p = 1.00. One exploratory run: not significant evidence either way at this n.
Best single option on EVAL, chosen after the fact (optimistic): `single@1` 1/16.

## What the selector learned (posterior mean pass rate per category)

| Category | TRAIN runs | single@1 | repair@1 | selftest@1 | Pick |
|---|---|---|---|---|---|
| arrays | 4 | 0.14 | 0.11 | 0.34 | `selftest@1` |
| data_structures | 4 | 0.08 | 0.32 | 0.22 | `repair@1` |
| dynamic_programming | 4 | 0.08 | 0.42 | 0.16 | `repair@1` |
| graphs | 4 | 0.10 | 0.13 | 0.12 | `repair@1` |
| greedy | 4 | 0.08 | 0.13 | 0.16 | `selftest@1` |
| hash_maps | 4 | 0.08 | 0.19 | 0.34 | `selftest@1` |
| numerical | 6 | 0.14 | 0.09 | 0.11 | `single@1` |
| recursion | 2 | 0.39 | 0.19 | 0.45 | `selftest@1` |
| sorting_search | 4 | 0.14 | 0.11 | 0.12 | `single@1` |
| strings | 6 | 0.08 | 0.11 | 0.12 | `selftest@1` |

## TRAIN stream

| # | Task | Category | Option | Result | Calls |
|---|---|---|---|---|---|
| 1 | seed-str-05 | strings | selftest@1 | ❌ 3/16 | 4 |
| 2 | seed-str-05 | strings | single@1 | ❌ 10/16 | 1 |
| 3 | seed-sort-03 | sorting_search | selftest@1 | ❌ 3/5 | 2 |
| 4 | seed-sort-03 | sorting_search | repair@1 | ❌ 0/5 | 4 |
| 5 | seed-str-04 | strings | single@1 | ❌ 0/6 | 1 |
| 6 | seed-str-04 | strings | repair@1 | ❌ 0/6 | 4 |
| 7 | seed-hash-03 | hash_maps | selftest@1 | ❌ 2/6 | 4 |
| 8 | seed-hash-03 | hash_maps | single@1 | ❌ 2/6 | 1 |
| 9 | seed-ds-02 | data_structures | single@1 | ❌ 0/3 | 1 |
| 10 | seed-ds-02 | data_structures | repair@1 | ✅ 3/3 | 1 |
| 11 | seed-greedy-03 | greedy | repair@1 | ❌ 0/8 | 4 |
| 12 | seed-greedy-03 | greedy | single@1 | ❌ 2/8 | 1 |
| 13 | seed-arr-01 | arrays | selftest@1 | ✅ 7/7 | 2 |
| 14 | seed-arr-01 | arrays | repair@1 | ❌ 4/7 | 4 |
| 15 | seed-num-05 | numerical | selftest@1 | ❌ 0/9 | 4 |
| 16 | seed-num-05 | numerical | repair@1 | ❌ 0/9 | 4 |
| 17 | seed-arr-03 | arrays | selftest@1 | ❌ 0/6 | 4 |
| 18 | seed-arr-03 | arrays | repair@1 | ❌ 1/6 | 4 |
| 19 | seed-sort-02 | sorting_search | selftest@1 | ❌ 1/7 | 4 |
| 20 | seed-sort-02 | sorting_search | repair@1 | ❌ 1/7 | 4 |
| 21 | seed-graph-01 | graphs | single@1 | ❌ 1/6 | 1 |
| 22 | seed-graph-01 | graphs | selftest@1 | ❌ 0/6 | 4 |
| 23 | seed-hash-01 | hash_maps | single@1 | ❌ 3/6 | 1 |
| 24 | seed-hash-01 | hash_maps | selftest@1 | ✅ 6/6 | 2 |
| 25 | seed-num-03 | numerical | repair@1 | ❌ 0/7 | 4 |
| 26 | seed-num-03 | numerical | selftest@1 | ❌ 0/7 | 4 |
| 27 | seed-graph-02 | graphs | repair@1 | ❌ 3/5 | 4 |
| 28 | seed-graph-02 | graphs | selftest@1 | ❌ 0/5 | 4 |
| 29 | seed-num-02 | numerical | selftest@1 | ❌ 0/6 | 4 |
| 30 | seed-num-02 | numerical | repair@1 | ❌ 0/6 | 4 |
| 31 | seed-rec-02 | recursion | selftest@1 | ✅ 5/5 | 2 |
| 32 | seed-rec-02 | recursion | single@1 | ✅ 5/5 | 1 |
| 33 | seed-dp-02 | dynamic_programming | single@1 | ❌ 1/6 | 1 |
| 34 | seed-dp-02 | dynamic_programming | selftest@1 | ❌ 0/6 | 4 |
| 35 | seed-greedy-01 | greedy | selftest@1 | ❌ 3/6 | 4 |
| 36 | seed-greedy-01 | greedy | single@1 | ❌ 0/6 | 1 |
| 37 | seed-dp-01 | dynamic_programming | single@1 | ❌ 3/7 | 1 |
| 38 | seed-dp-01 | dynamic_programming | repair@1 | ✅ 7/7 | 1 |
| 39 | seed-str-02 | strings | repair@1 | ❌ 0/8 | 4 |
| 40 | seed-str-02 | strings | selftest@1 | ❌ 0/8 | 4 |
| 41 | seed-ds-01 | data_structures | repair@1 | ❌ 0/4 | 4 |
| 42 | seed-ds-01 | data_structures | single@1 | ❌ 0/4 | 1 |

## EVAL per task

| Task | single@1 | repair@1 | selftest@1 |
|---|---|---|---|
| seed-arr-02 | ❌ (1) | ❌ (4) | ❌ (4) |
| seed-arr-04 | ❌ (1) | ❌ (4) | ❌ (4) |
| seed-dp-03 | ❌ (1) | ❌ (4) | ✅ (4) |
| seed-dp-04 | ✅ (1) | ❌ (4) | ❌ (4) |
| seed-ds-03 | ❌ (1) | ❌ (4) | ❌ (4) |
| seed-graph-03 | ❌ (1) | ✅ (1) | ❌ (4) |
| seed-graph-04 | ❌ (1) | ❌ (4) | ❌ (4) |
| seed-greedy-02 | ❌ (1) | ❌ (4) | ❌ (4) |
| seed-hash-02 | ❌ (1) | ❌ (4) | ❌ (4) |
| seed-hash-04 | ❌ (1) | ❌ (4) | ❌ (4) |
| seed-num-01 | ❌ (1) | ❌ (2) | ❌ (2) |
| seed-num-04 | ❌ (1) | ❌ (4) | ❌ (4) |
| seed-rec-01 | ❌ (1) | ❌ (4) | ❌ (4) |
| seed-sort-01 | ❌ (1) | ❌ (4) | ❌ (4) |
| seed-str-01 | ❌ (1) | ❌ (4) | ❌ (4) |
| seed-str-03 | ❌ (1) | ❌ (4) | ❌ (4) |

Cells: hidden-test verdict (model calls used).

Selftest: 54 generated tests kept over 32 runs.

Tokens: 116981 input, 95054 output. Wall time in the jsonl files includes free-tier pacing and retry waits.
