# G02 Fault Lab Runbook

## Boundary

This runbook is owned by I-0017. It starts only the digest-pinned OpenTelemetry Demo lab in the
private `fw-sut` namespace and binds it to the full business candidate SHA, the frozen upstream
commit, and the image-set digest. The checkout may be that candidate or its exact validated
evidence-only descendant under the dual-SHA protocol. It does not create G02 identities,
ground-truth or locked-test storage, baselines, model calls, or Gate evidence.

## Start

Run from a clean candidate checkout after the private host pin and dedicated SSH credential have
already passed the G01 bootstrap contract:

```text
uv run python -m faultwitness_dev lab-g02 start --profile private-server
```

The owner host downloads the generated upstream K3s manifest from exact commit
`b74a7bc7bbe66099c61951f42b24dab8b6f02d18`, verifies its SHA-256, and stages it through the
existing host-pinned SSH channel. Docker Hub images are pulled for `linux/amd64` by the already
pinned crane binary and imported into K3s before apply; this is the registered path for the private
host's Docker Hub reachability failure. OCI-layout archives preserve the upstream manifest digest
through K3s import; converted tarball digests are rejected. Remote archives are cached by their own
OCI tar digest, so an unrelated image-set change cannot invalidate and retransmit every archive.
I-0032 extends this same inventory with exactly the two digest-pinned helper images declared by
`config/g02/gate-probes.yaml`. SUT and probe references share one deduplicated OCI staging/import
contract. Existing SUT archive keys remain stable; probe archives use the `probe-*` namespace so
the distinct SUT and probe BusyBox digests cannot overwrite each other. Probe Pods must never
depend on a later direct registry pull from the private node.
The runner replaces complete image scalar values
with their registered digests, applies every namespaced resource to `fw-sut`, waits for all
Deployments and OpenSearch, and writes `fw-g02-candidate-binding`.

Service images follow the generated manifest's declared runtime contract. Two intentional,
digest-pinned 2.2.0 capability exceptions satisfy the frozen six-adapter scope: Flagd UI provides
`GET /api/read` and `POST /api/write`, and Email plus the exact upstream `emailMemoryLeak` flag
definition provides the memory-growth adapter. The generated manifest's older assets expose neither.

The registered `docker-compose.minimal.yml` path is a pre-candidate fallback only. Selecting it
requires a new candidate configuration; the runner never switches profiles during an incident.

## Inject and restore

The candidate-bound controller changes one allowlisted flag through Flagd UI and stores the exact
original document in the repository-external I-0017 operation journal:

```text
uv run python -m faultwitness_dev lab-g02 inject --fault-class productCatalogFailure
uv run python -m faultwitness_dev lab-g02 restore --operation-id <operation-id>
```

Injection writes the private snapshot before mutation and requires complete API readback. Restore
accepts only an `injected` operation from the current candidate and requires the restored canonical
digest to equal the original digest. Observation failure never skips restore.

For `kafkaQueueProblems`, the observer reads both the exported record-lag gauge and the exported
consumer last-poll age, and uses the greater value as the consumer-lag signal. The pinned SUT can
prefetch a record before its injected processing delay, so record lag alone may remain zero while
the consumer is demonstrably behind. Correlation requires the exact Fraud Detection fault log
`FeatureFlag 'kafkaQueueProblems' is enabled, sleeping` or an error span/log; an unrelated log line
cannot satisfy the oracle. The value must still exceed its pre-injection baseline in each of the two
frozen observations. This is signal-source correction only and does not alter N, the 30-second
spacing, the 90-second oracle window, or any performance or Gate threshold.

## Failure and compatibility semantics

- Source or image digest drift: blocking candidate failure; do not fetch a floating replacement.
- Cluster, DNS, TLS, registry, or SSH transport loss: `infra_failed`; retry only the affected
  bootstrap attempt.
- Any unpinned image remaining before apply: blocking failure with `FW_G02_UNPINNED_IMAGE`.
- A workload remains under observation while rollout is progressing; elapsed wall time alone is
  never `infra_failed` or `metric_fail`. A terminal Kubernetes error is attributed to that workload,
  and verified loss of progress is recorded before an operator or project owner stops the run.
- Compatibility and rollout attempts have no count or time ceiling. Record every attempt and its
  attribution; fix a deterministic root cause before retrying and retry unchanged work only for a
  classified transient infrastructure failure. Failed attempts remain evidence.
- Fetch, transfer, import, bootstrap, readiness, Iteration Eval, and Gate phase processes have no
  preset kill timeout. This changes orchestration only: all Eval N values, oracle windows,
  performance metrics, quality thresholds, paid budgets, and pass criteria remain frozen.
- Readiness waits on observed generation, desired/updated/ready/available replicas, and StatefulSet
  revision convergence. It does not consume Deployment `ProgressDeadlineExceeded` as a terminal
  result because that condition is itself wall-clock-derived and Pods may still converge afterward.

The destructive Gate scenario phase remains separately guarded and runs only once for an exact
candidate, image, config, and environment cache key.

## Gate phase interfaces

I-0017 owns executable handlers for both `lab-deploy-and-bind` and `scenario-matrix` before I-0020
starts. The deployment handler performs the existing digest-pinned clean-clone deployment, verifies
the candidate and SUT image-set binding, and writes its phase summary. The scenario handler executes
exactly the 32 registered seeds against that bound lab, restores the exact flag document after every
seed, and writes one candidate-bound atomic trial record plus one sealed observation packet per seed.

The deployment handler receives both `candidate_sha` and the binding's `evidence_head_sha`. It
requires checked-out HEAD to equal that evidence head and proves the business candidate is its Git
ancestor. The earlier candidate-binding phase separately verifies the exact changed-path allowlist
and subject digests. Thus the post-candidate binding asset cannot impersonate a new runtime candidate.

Passed scenario trial IDs are reused for the same phase key. Only pending or infrastructure-failed
work may continue; a metric/oracle/cleanup failure requires a new candidate. The phase itself is
destructive and can pass only once for one candidate/artifact/config/environment cache key.
