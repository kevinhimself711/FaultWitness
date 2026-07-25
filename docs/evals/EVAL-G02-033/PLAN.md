# EVAL-G02-033 Plan — Prior-Recovery Precondition Corrective

## Purpose

Verify the Master Plan's adjacent-seed recovery inheritance without changing health semantics or
running a Gate L2 matrix.

## Frozen checks

1. The first seed still requires an explicit healthy control observation.
2. Two healthy recovery observations may prove only the immediately following seed precondition.
3. Missing or unhealthy prior recovery fails closed.
4. Existing tests cover allow and reject branches.
5. One candidate-bound SEED-G02-0004 real seam consumes the preserved SEED-G02-0003 recovery,
   reaches FAULT_ACTIVE twice, restores the exact flag document, and recovers twice.
6. Gate L2, the full scenario phase, baselines and model calls remain zero; `open_evidence: []` is
   required.
