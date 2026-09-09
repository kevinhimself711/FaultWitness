---
paths: ["src/faultwitness_dev/g0*.py", "docs/evals/**"]
---

## Experiments and evidence

- Persist every live or multi-trial result atomically with provenance and artifact digests.
- When a semantic fix starts a new execution, preserve the prior terminal record and its last
  side-effect/observation checkpoints in the same trial journal history.
- Resume pending or infrastructure-failed trials. Do not discard passed independent trials after a
  transport failure or an unrelated fix.
- Cache and invalidation use named semantic checkpoints such as `sut`, `identity_and_storage`,
  `trace_service`, and `model_route`. A global Git SHA or aggregate evaluator digest is provenance,
  not a reason to invalidate every phase.
- Record the actual producer commit, image/config/dataset/model/locked-test/Ground-Truth digests,
  environment facts, timestamps, inputs, outputs, and artifact digests with the experiment.
- Every per-case `results.json`, `metrics.json`, `journal-index.json`, and `summary.json` is stored
  byte-for-byte regardless of size. A 5MB limit applies only to regenerable logs, trace dumps, and
  raw packets. Redact credentials, internal IPs, hostnames, and absolute local paths only; never
  redact numbers, case IDs, or labels.
- Prove the instrument before spending model budget, cheapest check first: (1) leakage probe, can a
  zero-model classifier over the same inputs reach the target score; (2) divergence, do the
  comparison arms separate at all and is the interval width non-zero; (3) disclosure symmetry, is
  every scoring rule stated to every measured arm, and does no comparison arm receive by
  construction what the others must infer. Only then buy trials.
- Disclosure symmetry is a blocking check because its failure mode is a *passing* gate. A rubric the
  measured arms were never told, which a comparison arm satisfies by construction, manufactures the
  separation the statistical criterion exists to detect.
- Pre-register the expected numbers and the expected verdict before a scored run, then record the
  measured outcome even when it falsifies them. A recomputation is not a measurement; state that in
  the pre-registration so the result cannot be reinterpreted afterwards.
- Destructive and soak work executes once for unchanged semantic checkpoints. Freeze pass,
  metric-fail, infrastructure-fail, attribution, and cleanup semantics in the Gate Plan.
- Do not kill normally progressing work with a preset wall-clock timeout. Stop only at a terminal
  result, deterministic failure, verified loss of progress, or owner cancellation. This rule never
  changes Eval N, thresholds, health windows, token/cost ceilings, or failure semantics.
- A zero-tolerance criterion must name a runner, a negative fixture, and a reviewable artifact.
- Once a root cause is known, no operator-adjudicated pass path remains; fix and replay normally.
