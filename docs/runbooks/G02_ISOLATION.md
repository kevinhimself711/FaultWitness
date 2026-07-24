# G02 Isolation Runbook

## Boundary

I-0018 froze the storage, identity, namespace, package, and evidence contracts needed to keep
ground truth and locked tests outside Agent and ordinary-developer reach. EVAL-G02-008 later proved
that its Gate handlers lacked executable candidate-bound provisioners and collectors; I-0024 owns
that forward implementation correction. Neither Iteration materializes any of the 160
preregistered cases, calls a model, or runs the Gate-layer 60-cell/6-stage/22-surface matrices.

## Storage and identity layout

The single `faultwitness-eval` bucket is divided into five non-overlapping G02 prefixes:
`g02/scenarios/`, `g02/trials/`, `g02/ground-truth/`, `g02/locked-tests/`, and `g02/evidence/`.
The policy source is `config/g02/isolation.yaml`; default deny applies when no allow rule matches,
and an explicit deny always overrides an allow.

- `scenario-controller` runs in `fw-sut`, reads scenario specifications, writes observations/trials,
  and can change only the six registered flags. It cannot read GT, locked tests, or product schemas.
- `baseline-agent` runs in `fw-baseline`, reads one observation packet, writes through its own trial
  sink, and reaches read-only observability endpoints. It has no network route to `fw-eval`.
- `sealed-evaluator` runs in `fw-eval`, reads trials/GT/locked objects and writes evidence. Its only
  data-plane egress is DNS plus MinIO in `fw-data`; it cannot reach or mutate `fw-sut` and cannot use
  baseline execution credentials.
- `ordinary-developer` is an external negative principal. It can read public documentation and the
  metadata-only preregistry, but no product schema, private trial/evidence, GT, or locked object.

`deploy/g02/isolation-policy.yaml` freezes the three service accounts with token automount disabled,
default-deny NetworkPolicies, baseline-to-observability egress, and evaluator-to-MinIO egress. It
contains no Secret. MinIO credentials and policies are provisioned out of band only when the unified
Gate candidate is frozen.

I-0022 adds only the reachability that EVAL-G02-005 proved missing. `baseline-agent` may reach
Prometheus `9090`, Loki `3100`, and Tempo `3200` in `fw-observability`; the matching ingress requires
both the `fw-baseline` namespace and the `baseline-agent` principal label. Public LangSmith access is
TCP `443` only and excludes private, loopback, link-local, metadata, carrier-grade NAT, documentation,
benchmark, multicast, and reserved IPv4 ranges. The policy still has no route to `fw-eval`, GT,
locked-test, or private evidence storage. The I-0022 negative fixture
`tests/fixtures/g02/isolation_broad_private_egress.yaml` proves that a broad private-network rule is
rejected before any live Gate phase runs.

## Preregistration and sealed packages

The preregistry is exactly 160 rows: four families by five difficulties, with four `dev`, two
`validation`, and two `locked` rows per cell. A row contains only ID, family, split, difficulty, and
the G07 ground-truth placeholder. The I-0018 runner rejects payload/answer fields and any
materialized `CORE-*` object.

The scenario-controller, baseline-agent, and sealed-evaluator package contexts are explicit file
allowlists. The package scanner rejects path or content evidence for ground truth, locked cases, or
the preregistry. Credentials are runtime-only mounts and never package inputs.

## Gate runner protocol

I-0024 correctively owns the complete execution path behind three candidate/environment-bound Gate
phase interfaces while preserving I-0018's frozen validators and Iteration evidence:

- `g02.access_matrix`: exactly 60 access cells over six schemas, five prefixes, four observability
  targets, and four probes per target.
- `g02.stage_matrix`: all six correlated `api`, `persistence`, `outbox`, `checkpoint`, `model-stub`,
  and `export` stages.
- `g02.canary_matrix`: zero hits on all 22 frozen persistence/egress surfaces.

The runner provisions only named credential references and live targets, then produces raw probe
documents under the repository-external candidate journal. Gate handlers invoke the collector
directly; operator-precomputed `phase_inputs` are not an execution path. Each phase validates
candidate SHA, environment fingerprint, exact enumeration, expected result, and an artifact
reference before atomically writing its reviewable matrix under the active standard orchestration's
Eval asset. A missing capability, wrong allow, missing stage, leaked canary, missing artifact
reference, or binding mismatch is blocking with no operator pass path.

EVAL-G02-005 and EVAL-G02-008 are immutable failed history. Replacement orchestration writes new
Gate artifacts only under `EVAL-G02-010`; no runner may select either terminal Eval or overwrite
its phase records.

These phases have no preset orchestration timeout. The rule changes only process supervision:
matrix N, zero-tolerance semantics, quality/performance thresholds, and all Gate criteria remain
unchanged.
