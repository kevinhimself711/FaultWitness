# EVAL-G02-001 Plan — Eval Protocol and Phase Engine

## Purpose

Close I-0016 by proving the deterministic phase state machine, atomic journal, resume semantics,
double-SHA negative paths, manifest debt runner, and reconciliation runner before candidate freeze.

## Validation set

- V-G02-001 at L1 with five state-transition fixtures.
- Runner/fixture/interface readiness for L2 V-G02-002, V-G02-003, and V-G02-016.

No unified candidate, deployment, destructive action, or live model call is permitted. L2 actual
evidence remains EVAL-G02-005 work and is not recorded as open Iteration evidence.

## Pass criteria

- All five L1 fixtures pass.
- Every owned L2 runner rejects its named negative fixture and exposes the frozen phase interface.
- `open_evidence` is empty at Iteration closure.

The command writes only the registered phase-contract artifact. Gate L2 runner execution remains
blocked by the I-0020 lifecycle guard.
