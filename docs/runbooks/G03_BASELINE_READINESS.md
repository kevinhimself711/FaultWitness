# G03 metric-v3 baseline readiness

This runbook produces non-Gate readiness evidence. It never edits or reinterprets a closed G02
asset. [AMD-0007](../blueprint/AMENDMENTS/AMD-0007.md) is the frozen definition.

## Preconditions

- `verify-bootstrap` can read the SSH and Bailian credentials.
- The G02 SUT is deployed and reachable. Its identity comes from two places, not one:
  `latest_release.producer_commit` in `PROJECT_STATE.yaml` is the producer SHA recorded in the
  run manifest, while the namespace, endpoint, and image set come from `config/g02/lab.yaml`
  via `validate_lab_bootstrap`. `PROJECT_STATE.yaml` carries no SUT namespace or endpoint field
  and its schema forbids one. Deploy with `deploy-g02-lab` and confirm every workload reports
  Ready before starting a replay.
- The host that will produce the evidence is recorded, per ADR-0016 and ADR-0017. Evidence from
  a different host is not comparable and must not be resumed into.
- `docs/audit/**` and the frozen G02 assets match the recorded start hashes. Both trees are
  re-hashed at the end of every run, so **no write to `docs/audit/**` or the frozen G02 assets
  may overlap a live run**, and neither may any edit to metric-v3 source: the collector and
  observer source digests are checked during scenario cleanup, so editing them mid-run fails
  the run at the end rather than the start.
- All metric-v3 code, configuration, tests, packet shape, and acceptance rules are complete.

## Preflight and mandatory stop

Choose a new empty directory under `.audit/g03-readiness/`:

```text
uv run python -m faultwitness_dev retest-baselines-v3 \
  --output-dir .audit/g03-readiness/<RUN_ID> \
  --skip-live
```

Preflight performs the only privileged replay. It writes the 32 fresh scenarios, the canonical
metric definition and digest, independent deterministic results, packet completeness, presence
probe, ambiguity list, per-case four-turn input upper bounds, run identities, and a preflight
summary. It makes no model calls.

The frozen v3 collector resolves exactly one current `ad-` and `email-` pod for every case and uses
exact-pod CPU and memory selectors. Zero or multiple matching pods fail closed; wildcard fallback
is forbidden. The two fault windows are separated by 65 seconds for every fault class. If a fault
window reaches its activation deadline, its terminal observation is retained for interval and
cleanup bookkeeping but does not convert the failed fault-state predicate into a pass.

For `adHighCpu` the control phase waits for a quiescent ad pod before sampling the baseline: CPU at
or below 0.25 cores, polled every five seconds, with a 240-second deadline. The CPU query is a
two-minute `rate()` and recovery never requires a return to rest, so without this wait a case
starting within about three minutes of the previous `adHighCpu` case inherits that case's burn as its
baseline and, multiplied by the frozen 5.0 activation multiplier, faces a bar the pod cannot reach. A
pod that never settles is an `InfrastructureFailure`. The multiplier and minimum are unchanged.

The fault and recovery windows drive their own workload: metric v3 issues exactly one
candidate-bound request for the sealed label on every poll tick, symmetric across all six classes,
so activation never depends on incidental load-generator traffic. Every `fault_state` and
`recovery_state` predicate is unchanged; repeated stimulus can only remove false negatives, and a
per-label negative test asserts that with the flag off the oracle stays non-active no matter how
many requests are issued. The activation deadline remains 90 seconds. The recovery observation
deadline is 240 seconds with 65-second spacing, both pre-registered in the collector contract.

An absent Prometheus series is reported as null and named in `absent_series`, never scored as an
observed `0.0`. A window with any absent series is unscoreable rather than failed: every phase polls
at the five-second interval, re-driving its own workload, until all six evidence groups are present.
The wait is label-blind, so the poll count never depends on the sealed label. Only a series still
absent at that phase's pre-registered observation deadline fails the case as `InfrastructureFailure`,
which AMD-0003 authorises for unlimited attributable retries; metric failures remain blocking and
no retry budget exists. A `FW_G03_COLLECTOR_` fail-closed marker propagates as a governance error
and is never reclassified as infrastructure.

When a case fails, its journal payload retains the healthy windows, whichever fault and recovery
observations were obtained, and the per-observation truth of every predicate term for that label,
so the failure is attributable without a second live run. If both the fault oracle and cleanup
fail, the primary cause is reported first with the cleanup failure carried alongside it.

Stop after this command. Inspect at least:

- `preflight_status`;
- `dataset_digest` and all frozen identity digests;
- six-group completeness;
- Top-1 `8/32` and Top-3 no greater than `20/32`;
- ambiguity count and case IDs;
- deterministic point estimate and interval; and
- maximum/P95 input bound with at least 10% headroom.

Presence and deterministic evaluation are completed before any live credential read or model
request. A presence Top-3 of `32/32`, or a deterministic core-e2e point estimate of exactly
`1.000`, is a hard pre-live stop and must be reported without buying live trials.

The only choices are to preserve the preflight permanently or resume the same directory. Any
source, configuration, AMD, packet, formula, or repetition-rule change invalidates resume and
requires a new empty directory and fresh replay.

## Three-repetition live reference

After the explicit human decision:

```text
uv run python -m faultwitness_dev retest-baselines-v3 \
  --output-dir .audit/g03-readiness/<RUN_ID> \
  --resume \
  --repetitions 3
```

Resume recomputes the runtime metric definition and verifies the scenarios bytes, dataset, v3
configuration, AMD, relevant source, producer, SUT, model, and checkpoint identities before
credential or model use. It does not replay scenarios.

Each of `no_rag`, `naive_react`, and the unregistered `naive_react_single` ablation runs 96 trials.
`naive_react` uses two to four correction turns under one cumulative trial budget. The ablation is
reported but is excluded from `best_baseline` and readiness.

## Five-repetition extension

The r3 aggregate sets `extension_authorized: true` only when deterministic-vs-live significance is
the sole failed hard condition. Only then run:

```text
uv run python -m faultwitness_dev retest-baselines-v3 \
  --output-dir .audit/g03-readiness/<RUN_ID> \
  --resume \
  --repetitions 5
```

This appends repetitions four and five to the same journals. It never changes the r3 artifacts.
Five repetitions are final.

## Failure and evidence semantics

`budget_exhausted`, `output_truncated`, and `malformed` are separate scored failures and stay in the
denominator. Infrastructure, fallback, route, and abnormal termination failures are resumable and
must reach complete `96/96` or `160/160` arm counts.

Every command atomically saves evidence before a blocked non-zero exit. `execution_status`,
`preflight_status`, `readiness_status`, and `blocked_reason` are independent. Paths at or below
`.audit/g03-readiness/invalidated/`, including resolved links and `..`, fail closed.

Readiness is `ready` only when all AMD-0007 hard conditions pass. Even then, G03 stays
`not_started` until a separate decision-complete Master Plan is frozen.

## Diagnostic scan mode

`--continue-on-case-failure` exists to expose the whole failure spectrum in one pass instead of one
case per round. It requires `--skip-live`, makes no model calls, and does not alter default
behaviour:

```text
uv run python -m faultwitness_dev retest-baselines-v3 \
  --output-dir .audit/g03-readiness/<DIAGNOSTIC_ID> \
  --skip-live \
  --continue-on-case-failure
```

Failing cases are recorded with their diagnostics and skipped; the remaining cases still run; every
case outcome is written to the journal and the summary. Products are stamped `diagnostic_only: true`
and `promotable_to_gate_evidence: false`, and are refused as a `--resume` source.

A diagnostic-mode product may never be promoted to readiness evidence. Readiness still requires a
new empty directory and a single clean 32-case replay under abort-on-first-failure semantics.
