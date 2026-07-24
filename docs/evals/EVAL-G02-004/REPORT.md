# EVAL-G02-004 Report

## Result

Result: pass.

Implementation candidate `c4fa561ad58c5d8da0127fae8f0d0720eec15f76` passed all four I-0019
checks with `open_evidence: []`. The Eval executed exactly five scorer fixtures, all seven frozen
quality-floor entries, three deterministic non-seed cases, and four paid non-seed live trials. It
did not use any Gate seed or run the Gate N=32/N=192 matrices.

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
passing trials used 652 input and 447 output tokens and cost 0.00488 CNY at the frozen price. Each
trial has an atomic candidate-bound journal record.

One controlled request-preflight transport interruption was recorded for
`no_rag/synthetic-live-a`. The other completed trial remained immutable; only the interrupted trial
resumed and then passed. The interrupted trial has attempt count four because each state transition
(`running`, `infra_failed`, `running`, `pass`) is atomically journaled. No preset orchestration
wall-clock timeout was used. The frozen one internal transient retry, token caps, latency
measurement, quality metrics, and Gate criteria were unchanged.

## Preserved negative candidate

The first candidate `b448c5cf9378caa2e2c96e31ea9640205972deb4` made four paid calls, using
520 input and 340 output tokens at 0.00376 CNY. All four responses renamed `evidence` to
`evidence_ids`; the validator incorrectly defaulted the missing field to an empty list and reported
pass. The run is invalidated as a harness failure and its journals are preserved under
`artifacts/attempts/b448c5cf9378caa2e2c96e31ea9640205972deb4/`.

The verified root cause was fixed by enforcing the complete structured-result schema and binding
trial IDs to the full candidate SHA. A new candidate was created and only EVAL-G02-004 was rerun.
No operator-adjudicated pass, sample increase, threshold change, fallback, or hidden negative result
was used. Across both candidates, I-0019 consumed 1,172 input and 787 output tokens and 0.00864 CNY,
well below the frozen retry contingency.

## Open evidence

None. Gate-layer N=32 deterministic and N=192 live execution is future unified-candidate scope, not
Iteration open evidence.
