# EVAL-G02-004 Report

## Result

Result: pass.

Corrective implementation candidate `4bcc990c6b51d39736c81768199844b95f1a8c69` passed all four I-0019
checks with `open_evidence: []`. The Eval executed exactly five scorer fixtures, all seven frozen
quality-floor entries, three deterministic non-seed cases, and four paid non-seed live trials. It
did not use any Gate seed or run the Gate N=32/N=192 matrices.

This rerun was required because the pre-I-0020 readiness audit found that the prior Gate handlers
validated imported baseline JSON instead of producing the frozen matrices. The corrective candidate
adds the direct N=32 deterministic, N=192 trial-local live, and sealed aggregate execution paths and
their offline contract test. EVAL-G02-004 exercised only its unchanged Iteration N=3/N=4 layer.

## Scorer, thresholds, and deterministic baseline

- V-G02-012 classified the correct, wrong-root, malformed, unsupported-claim, and no-evidence
  branches exactly as registered.
- V-G02-013 retained all seven authoritative operators and values, including the strict `< 1%`
  dead/no-progress-loop floor. No threshold changed.
- V-G02-014 ran exactly N=3: correct, wrong-root, and malformed cases. The deterministic workflow
  received no ground truth and makes no model call.
- The canonical packet builder exposes only the problem brief, case ID, stable observation IDs,
  observations, schema version, and packet digest. Sealed fields are rejected.

## Live baseline result

V-G02-015 ran exactly two non-seed cases across `naive_react` and `no_rag`, for N=4 paid trials.
Every call resolved to `qwen3.7-plus-2026-05-26` on Bailian with fallback count zero. The four
passing trials used 652 input and 460 output tokens and cost 0.004984 CNY at the frozen price. Each
trial has an atomic candidate-bound journal record.

One controlled request-preflight transport interruption was recorded for
`no_rag/synthetic-live-a`. The other completed trial remained immutable; only the interrupted trial
resumed and then passed. The interrupted trial has attempt count four because each state transition
(`running`, `infra_failed`, `running`, `pass`) is atomically journaled. No preset orchestration
wall-clock timeout was used. The frozen one internal transient retry, token caps, latency
measurement, quality metrics, and Gate criteria were unchanged.

## Preserved earlier candidates

The first candidate `b448c5cf9378caa2e2c96e31ea9640205972deb4` made four paid calls, using
520 input and 340 output tokens at 0.00376 CNY. All four responses renamed `evidence` to
`evidence_ids`; the validator incorrectly defaulted the missing field to an empty list and reported
pass. The run is invalidated as a harness failure and its journals are preserved under
`artifacts/attempts/b448c5cf9378caa2e2c96e31ea9640205972deb4/`.

The verified root cause was fixed by enforcing the complete structured-result schema and binding
trial IDs to the full candidate SHA. Candidate `c4fa561ad58c5d8da0127fae8f0d0720eec15f76`
then passed the same N=3/N=4 Eval with 652 input and 447 output tokens at 0.00488 CNY, but was later
superseded when readiness audit exposed the separate Gate-handler production-path defect described
above. Its passing evidence remains in Git history.

No operator-adjudicated pass, sample increase, threshold change, fallback, or hidden negative result
was used. Across all three candidates, I-0019 consumed 1,824 input and 1,247 output tokens and
0.013624 CNY, well below the frozen retry contingency.

## Open evidence

None. The Gate-layer N=32 deterministic and N=192 live runners are implemented and unit-tested, but
their execution remains future unified-candidate scope rather than Iteration open evidence.
