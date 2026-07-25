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

EVAL-G02-005, EVAL-G02-008, EVAL-G02-010, EVAL-G02-012, EVAL-G02-014, and EVAL-G02-016 are
immutable failed history. Replacement orchestration writes new Gate artifacts only under
`EVAL-G02-018`; no runner may select a terminal Eval or overwrite its phase records.

Provisioning is derived from `config/g02/gate-probes.yaml` and is checked by one identical local and
remote plan digest before any credential is created. The two probe images are digest pinned.
Both probe images must already have passed the same owner-host OCI archive, verified transfer, and
K3s containerd import path as the SUT images before provisioning starts. A direct Docker Hub pull
from the private node is not an accepted bootstrap dependency.
Credential values are generated on the private host, stored only in four candidate/environment-
bound Kubernetes Secrets, and never returned to the operator or written to Git. A stale candidate
binding disables the old MinIO user and PostgreSQL login before rotating it. Reprovisioning the
same binding is idempotent and resets each MinIO user before attaching only its exact policy;
`ordinary-developer` remains policy-free.

The 60 access cells execute live PostgreSQL, MinIO, Prometheus, Loki, Tempo, and LangSmith
operations. LangSmith keeps its API key on the operator: the baseline path proves public HTTPS
reachability from the `baseline-agent` pod, then the operator proves the existing credential;
negative pods never receive that credential. The trace collector submits one candidate-bound
six-span envelope, verifies all six correlated names in Tempo, and drains the existing operator
LangSmith relay. The canary collector injects both deterministic Secret and PII canaries into the
sanitizer rejection path, proves no queue delta, then scans current process output, HTTP/SSE/log
surfaces, PostgreSQL, Redis, MinIO, decoded Kubernetes objects, OTLP storage, Git, Eval assets, and
the public preregistry. Only canary digests and hit counts enter the matrix.

The trace reference and every timestamp in its envelope are replay-stable. The controller reads the
candidate commit timestamp once and includes it in trace/canary requests; the remote probe validates
that it is timezone-aware and uses it for `emitted_at`, `started_at`, and `ended_at`. Re-entering the
same candidate/environment operation therefore submits byte-equivalent content under the same trace
reference and receives the existing idempotent duplicate behavior instead of a payload conflict.
Access and provisioning requests do not depend on this timestamp. This changes no six-stage N,
required stage, export target, latency metric, or pass criterion.

Access trials persist one cell at a time. Trace and canary collections persist the collection plus
each stage or surface. A classified transport failure resumes only the failed/pending unit; an
allow mismatch, missing stage, canary hit, binding drift, missing artifact, or provisioning defect
is terminal for that candidate and has no retry or operator-pass route.

## Exact GetObject seam proof

Object-read cells use `mc cat <alias>/faultwitness-eval/g02/<prefix>/deny-sentinel >/dev/null`.
`mc stat` and directory-listing operations are forbidden because they can require `ListBucket`
before testing the frozen `GetObject` permission. Object-write cells continue to use `mc pipe`.

C-G02-001 closes only after one targeted real-client proof against the existing private G02 lab:

- `scenario-controller` reads the scenario sentinel through direct `mc cat` with the existing
  `GetObject`-only policy and no `ListBucket` grant;
- `ordinary-developer` invokes the same direct object operation and remains denied.

The proof artifact records only candidate/environment identity, client version, sanitized target,
allow/deny outcome, timestamps, and command/output digests. It never records credentials or object
content. This pair is external-seam compatibility evidence, not Gate L2 N and not permission to
skip or reduce the frozen 60-cell Gate matrix.

## LangSmith credential seam proof

The operator-side read probe uses the current official
`GET /api/v1/orgs/current/info` credential-authenticated contract; response content is never
retained. Unlike public `/api/v1/info`, this endpoint returns 401 without a credential and therefore
proves the existing key without requiring workspace query context. The public result contains only
candidate/environment identity, request-contract digest, `credential_allow`, a sanitized response
class, HTTP status, timestamps, and execution counters. Transport, 408/425/429, and 5xx remain
resumable infrastructure failures; 401/403 remain credential denial; any other non-success response
is a blocking request-contract defect rather than an access-policy result.

C-G02-002 executes this exact helper once with the existing repository-external credential. A
non-success result fails the corrective and never authorizes key replacement, expected-allow
relaxation, operator adjudication, or Gate L2 execution. The successful artifact path is
`docs/evals/EVAL-G02-025/artifacts/langsmith-access-seam-proof.json`.

## LangSmith TCP egress seam proof

The pod-side LangSmith cell is a network-authorization assertion, so it uses
`nc -z api.smith.langchain.com 443` and terminates on the transport connect result. It does not use
an HTTP downloader, inspect a response body, or receive the LangSmith credential. Prometheus,
Loki, and Tempo remain HTTP health operations through `wget`; the separate operator-side
credential-authenticated LangSmith read remains unchanged.

C-G02-003 first falsifies this transport abstraction on the existing probe pods, then repeats the
same three branches against the corrective candidate: `baseline-agent` must connect, while
`ordinary-developer` and `cross-boundary` must be rejected by the existing policy. The sanitized
artifact records candidate and environment binding, source and command digests, timestamps,
return classifications, and zero deployment/model accounting. It contains no credential, response
body, Pod IP, private endpoint, or secret. This is targeted real-seam evidence, not execution or
reduction of the 60-cell Gate matrix. The artifact path is
`docs/evals/EVAL-G02-027/artifacts/langsmith-tcp-egress-seam-proof.json`.

These phases have no preset orchestration timeout. The rule changes only process supervision:
matrix N, zero-tolerance semantics, quality/performance thresholds, and all Gate criteria remain
unchanged.
