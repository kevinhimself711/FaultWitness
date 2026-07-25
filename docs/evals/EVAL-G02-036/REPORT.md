# EVAL-G02-036 Report

Result: `fail` on candidate `0ef51cdb5987aa8b1c5cf17e712fe513f1d33b74`.

Candidate binding, 23-subject static verification, candidate-bound trace-service/lab deployment,
and the explicitly inherited 60-cell isolation, six-stage trace, and 22-surface canary evidence all
passed. The lab had 24/24 Ready Deployments and an exact candidate-bound Ready trace service.

Scenario seeds 1–7 were inherited with `attempt: 0`. Seeds 8–12 executed once and passed, including
two independent `emailMemoryLeak` cases. `SEED-G02-0013/kafkaQueueProblems` terminated the
destructive phase with `fault oracle did not reach FAULT_ACTIVE`.

The flag injection, exact restoration, journey health, and Kafka feature-flag sleep log all worked.
Historical Prometheus evidence showed consumer lag remained zero during the frozen 90-second
deadline and became positive only after incidental load-generator checkout traffic arrived. The
runner did not create a deterministic Kafka workload after injection. This is a runner-control defect,
not an infrastructure failure, and the deadline, oracle, N, and failure semantics remain unchanged.

The scenario phase executed once for the exact candidate key. Seeds 14–32, deterministic baseline,
the 192 live-model trials, aggregate, reconciliation, and close-readiness did not run. Model calls,
tokens, cost, fallback, waivers, and `open_evidence` are all zero.
