# EVAL-G02-037 Plan — Kafka Deterministic Workload Corrective

## Purpose

Prove that the existing Kafka fault path sends exactly one candidate-bound checkout before sampling,
then reaches the unchanged two-sample fault oracle and exact recovery on SEED-G02-0013.

## Scope

1. Run the existing Kafka-focused unit tests.
2. Deploy the exact corrective candidate with the existing lab deployer.
3. Execute only SEED-G02-0013 through `run_scenario` and the real remote flag/observer seam.
4. Record checkout count/status, two fault observations, two healthy recovery observations, and exact
   flag restoration.

No Gate L2 phase, full scenario matrix, baseline, or model call is in scope. N, spacing, deadline,
thresholds, permissions, and failure semantics remain unchanged.
