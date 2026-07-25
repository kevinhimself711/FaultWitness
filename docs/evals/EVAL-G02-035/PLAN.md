# EVAL-G02-035 Plan — Email-Memory Monotonic-Sample Corrective

## Purpose

Prove the two-sample email-memory state transition without changing the frozen oracle or running a
Gate L2 matrix.

## Frozen checks

1. The first memory sample is retained but cannot by itself produce `FAULT_ACTIVE`.
2. A second, larger sample after the existing spacing proves the original monotonic oracle.
3. A non-growing second sample remains non-active while cleanup has a valid comparator.
4. The other five fault observers are unchanged.
5. One candidate-bound `SEED-G02-0008` real seam reaches `FAULT_ACTIVE`, restores the exact flag
   document, and produces two healthy recovery observations.
6. Gate L2, baselines and model calls remain zero; `open_evidence: []` is required.
