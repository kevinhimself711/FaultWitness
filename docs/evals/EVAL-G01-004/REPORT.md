# EVAL-G01-004 Report

## Result

Result: pending (Windows candidate run passed; cross-platform evidence open).

Candidate `f81c7f07e4fbd0636eef669285588cbe7cceef20` passed the Windows deterministic run with artifact digest `58b7be07bec327e397c8956f46964a929a52e92ea4c243af00780f4cf706c791`. Counts were 21 core types, 12 support types, 52 states, 82 transitions, 34 Commands, 43 Events, and 10 Errors. All 82 legal transitions emitted unique deterministic decisions and 492 owner/actor/guard/version/idempotency mutations were rejected.

The first candidate run failed because explicit `guard:<TR-ID>` facts were absent from the Eval harness. The kernel correctly failed closed; fix commit `f81c7f0` bound those guards without weakening the registry or thresholds, and the new immutable candidate passed.

## Required evidence

- Full candidate SHA and cross-platform generation digests.
- Count/drift report, legal-transition conformance, mutation results, registry startup negatives, and compatibility report.

## Open evidence

Ubuntu/Windows byte-digest equality and the complete public OpenAPI/AsyncAPI compatibility result remain open. The local transition conformance, mutation, registry, strict-schema, and generated-resource checks are complete.
