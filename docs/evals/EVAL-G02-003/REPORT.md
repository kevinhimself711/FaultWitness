# EVAL-G02-003 Report

## Result

Result: pass.

Implementation candidate `bcc643774c4d8577f6181664b3bf19aa12a5f281` passed all five I-0018
checks with `open_evidence: []`. This Eval was deterministic and local-policy scoped. It did not
deploy credentials, read or create GT/locked case content, run a live Gate matrix, or call a model.

## Isolation scheme

The storage contract uses bucket `faultwitness-eval` with separate `g02/scenarios/`, `g02/trials/`,
`g02/ground-truth/`, `g02/locked-tests/`, and `g02/evidence/` prefixes. The runtime trust zones are
`fw-sut`, `fw-baseline`, and `fw-eval`.

Three service accounts have token automount disabled. Six NetworkPolicies establish default deny,
allow `baseline-agent` only DNS plus SUT observability ports, and allow `sealed-evaluator` only DNS
plus MinIO in `fw-data`. The manifest contains zero credential objects. MinIO credentials remain
out of band and are not provisioned by this Iteration.

## Four-identity result

- `scenario-controller`: scenario read and trial write controls passed; GT, locked-test, product
  schema, and non-flag SUT access were denied.
- `baseline-agent`: own observation/trial and read-only observability controls passed; GT and
  `fw-eval` network access were denied.
- `sealed-evaluator`: trial/GT/locked reads and evidence write controls passed; SUT mutation and
  baseline execution credentials were denied.
- `ordinary-developer`: public preregistry control passed; GT, locked, private trial, evidence, and
  product-schema access were denied.

The named wrong-allow fixture is `tests/fixtures/g02/access_wrong_allow.yaml`; it is rejected by the
same policy runner. The live credential-backed 60-cell matrix remains correctly reserved for the
unified Gate candidate under V-G02-009.

## Registry, package, and leakage result

V-G02-007 produced exactly 160 metadata-only rows: 80 dev, 40 validation, and 40 locked. Each row
contains only ID, family, split, difficulty, and a G07 placeholder URI. Materialized object count is
zero; no case or answer was generated.

V-G02-008 scanned exactly the three scenario-controller, baseline-agent, and sealed-evaluator
package allowlists. All passed with content digests and no GT, locked-test, preregistry, or case
payload. The negative package fixture containing a case/answer is rejected.

V-G02-011 tested all four new writer paths. Each safe control passed and each Secret/PII canary was
rejected before persistence. Artifacts contain only canary digests, never raw secrets or PII. The
Gate-layer 22-surface matrix remains reserved for the unified candidate.

## G01 carry-in

- DEBT-G01-001: I-0018 policy simulation passed; the 60-cell live matrix is Gate scope.
- DEBT-G01-002: six-stage runner, missing-stage fixture, phase interface, and binding are ready; the
  correlated live matrix is Gate scope.
- DEBT-G01-003: four new writer paths passed; the 22-surface live matrix is Gate scope.
- DEBT-G01-004: not covered because G02 does not execute the production Agent stage waterfall.

No G01 REPORT, manifest, CLAIMS asset, or tag was modified.

## Open evidence

None. Gate-layer L2/L3 execution is future unified-candidate scope and is not Iteration open
evidence.
