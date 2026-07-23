---
document_id: FW-GATE-G02-PLAN
gate: G02
status: frozen
plan_version: G02-master-plan-v1
authoritative: true
---

# G02 Gate Master Plan — Fault Laboratory and Baselines

## 1. Gate objective and budget

G02 freezes a reproducible fault laboratory and measurement baseline. It delivers four
Scenario DSL families, six fault classes, 32 executable seed scenarios, a 160-row core-case
preregistration, three baselines, deterministic scoring, and candidate-bound evidence. G02 does
not implement the read-only Agent vertical slice.

The minimum sufficient execution plan is five Iterations. Their estimates include Iteration Eval.

| Work | Expected duration |
| --- | ---: |
| I-0016 | 2h30 |
| I-0017 | 4h00 |
| I-0018 | 3h30 |
| I-0019 | 4h30 |
| I-0020, excluding Gate Eval | 0h30 |
| Iteration total | **15h00** |
| Gate Eval | **2h33** |
| Total | **17h33** |

If every live attempt consumes its one complete retry, the Gate Eval contingency is 3h18 and
the total contingency is 18h18. These are planning estimates, not execution stop conditions.
External waiting and every retry are reported as actual elapsed time under amended Section 11.

## 2. Scope, non-goals, and dependencies

### 2.1 In scope

- OpenTelemetry Demo 2.2.0 at commit
  `b74a7bc7bbe66099c61951f42b24dab8b6f02d18`, with every linux/amd64 image resolved to a
  digest before candidate freeze.
- Primary private-server K3s deployment and a preimplemented same-commit official
  `docker-compose.minimal.yml` fallback that may be selected only before candidate freeze.
- One-command clean-clone start, inject, and restore interfaces.
- Four Scenario DSL families, six flagd fault adapters, 32 executable seeds, their sealed seed
  ground truth, and canonical observation packets.
- Exactly 160 preregistration rows containing ID, family, split, difficulty, and a ground-truth
  location placeholder. Actual case materialization remains G07 scope.
- Deterministic workflow, Naive ReAct, and no-RAG baselines with deterministic scoring and 95%
  bootstrap confidence intervals.
- Manifest v2, phase/trial protocol, candidate/evidence identity, and evidence ownership plans.
  I-0016 implements those mechanisms later; this planning commit only registers the protocol.
- Three G01 supplemental evidence matrices that intersect the new G02 identities and storage
  surfaces: access, six-stage spans, and all-surface Secret/PII canaries.

### 2.2 Non-goals

- No generation or implementation of 160 core cases and no locked-case payload.
- No G03 Agent Runtime, LangGraph, product Tool Gateway integration, API, or Console.
- No Online Boutique, Chaos Mesh, Toxiproxy, or custom chaos framework.
- No RAG, TrajectoryIR, data flywheel, training, LLM judge, or human agreement study.
- No HA, scale, soak, performance certification, or G01 production wall-time reconciliation.
- No NewAPI live route and no three-model-family matrix.
- No claim that a baseline meets the frozen future Agent quality floors.

### 2.3 Dependencies

- The closed, waiver-free G01 platform and its nine immutable Eval manifests.
- Private-server K3s, MinIO, PostgreSQL, Prometheus, Loki, Tempo, LangSmith, SOPS/Age, SSH, and
  the existing ModelGateway.
- Bailian exact model `qwen3.7-plus-2026-05-26`, with a fixed route and no fallback.
- Project-owner approval for destructive runs, service-account creation, and paid live usage.

### 2.4 Required supporting scope that cannot wait for G03

| Supporting work | Why it cannot be deferred |
| --- | --- |
| Phase, resume, journal, and candidate-binding engine | G02 itself has 192 paid live trials. Deferral would recreate the monolithic, nonrecoverable final-audit harness failure. |
| Ground-truth and locked-test isolation | G02 first creates seed ground truth and a locked split boundary. Isolation must exist before those assets are produced. |
| Three G01 supplemental matrices | They are explicit carry-in and directly intersect G02 identities, prefixes, trial writers, and evidence writers. |

Everything else beyond the authoritative G02 definition is deferred.

## 3. Interfaces and versioning

Planned commands are:

```text
uv run python -m faultwitness_dev lab-g02 start --profile private-server
uv run python -m faultwitness_dev lab-g02 inject --scenario-id <SEED-ID>
uv run python -m faultwitness_dev lab-g02 restore --run-id <RUN-ID>
uv run python -m faultwitness_dev eval-iteration <ID> --candidate-sha <SHA>
uv run python -m faultwitness_dev eval-g02 --candidate-sha <SHA> [--phase <ID>] [--resume | --from-failed]
uv run python -m faultwitness_dev eval-g02-close --candidate-sha <SHA> --evidence-head-sha <SHA>
```

- Scenario DSL and preregistration schemas start at 1.0.0 and are versioned independently.
- G02 Eval manifests are planned as schema 2.0.0. The repository's current v1 manifest schema
  remains in force until I-0016 implements a backward-compatible migration.
- The governance planning asset schema is 1.1.0.
- Architecture, OpenAPI, AsyncAPI, state machines, and command/event contracts do not change.

## 4. Scenario DSL and seed catalogue

An executable seed contains:

```text
schema_version
scenario_id
family
difficulty
sut_release / sut_commit / image_set_digest
problem_brief
control_journey
fault_action {class, flag_key, variant}
observation_contract
fault_oracle
recovery_oracle
ground_truth_ref
```

The baseline receives only the Problem Brief and canonical observation packet. It never receives
`fault_action`, difficulty, split, ground-truth URI, or the full scenario document.

| DSL family | Fault class | Eight-seed allocation |
| --- | --- | --- |
| `change_config` | `productCatalogFailure` | 2 Easy, 2 Medium, 2 Hard, 1 OOD, 1 Adversarial |
| `resource_capacity` | `adHighCpu`, `emailMemoryLeak` | Four per class; CPU uses Easy-1/Medium-1/Hard-1/OOD and memory uses Easy-2/Medium-2/Hard-2/Adversarial |
| `dependency_network` | `paymentFailure`, `paymentUnreachable` | Four per class using the same slot rule |
| `runtime_data` | `kafkaQueueProblems` | 2 Easy, 2 Medium, 2 Hard, 1 OOD, 1 Adversarial |

Difficulty semantics are frozen:

- Easy exposes a direct error and complete correlated path.
- Medium removes one direct symptom while retaining sufficient cross-signal evidence.
- Hard adds one deterministic noncausal log or metric distractor.
- OOD uses a nondefault entry journey or time window.
- Adversarial adds correlated but noncausal conflicting evidence while retaining one true cause.

Runtime IDs are `SEED-G02-0001` through `SEED-G02-0032`. Their assignment is the sorted order of
`SHA-256("G02-seed-id-v1" || canonical(family, slot, fault_class))`, so the ID does not encode the
answer.

## 5. Core-case preregistration

The registry contains `CORE-0001` through `CORE-0160` and no payloads:

- Four families times five difficulties.
- Each family+difficulty cell has four dev, two validation, and two locked rows.
- Totals are 80 dev, 40 validation, and 40 locked.
- The placeholder URI is
  `s3://faultwitness-eval/g07/ground-truth/CORE-<NNNN>.json`.
- G02 must prove that none of those 160 placeholder URIs has a case or answer object.

## 6. Injection, health, and recovery semantics

The injector uses only flagd UI `GET /api/read` and `POST /api/write`. The scenario controller may
change only the six named keys and has no shell or arbitrary Kubernetes mutation permission.

The oracle is ternary: `HEALTHY`, `FAULT_ACTIVE`, or `UNKNOWN`. `UNKNOWN` never passes.

Every seed performs the following state sequence:

1. Save the exact original flag document and prove a healthy control journey.
2. Change exactly one allowlisted flag and read back the requested value.
3. Obtain two consecutive fault observations 30 seconds apart, within a 90-second deadline.
4. Restore the exact original document in `finally`.
5. Read back the original value and obtain two healthy recovery observations 30 seconds apart,
   within a 90-second deadline.

The prior seed's recovery observations may serve as the next seed's precondition. Cleanup failure
quarantines the environment and blocks every dependent phase.

| Fault class | Required `FAULT_ACTIVE` evidence |
| --- | --- |
| `productCatalogFailure` | Failed product-catalog journey plus a correlated service error span or log |
| `adHighCpu` | Two ad-service CPU-rate observations above the pre-injection window maximum, with correlated request spans |
| `emailMemoryLeak` | Working set rises at both post-injection observations under the fixed email workload |
| `paymentFailure` | Checkout payment failure plus a payment business-error span |
| `paymentUnreachable` | Checkout failure plus a correlated payment connection error |
| `kafkaQueueProblems` | Consumer lag above the pre-injection value plus a correlated Kafka consumer error |

Recovery requires original flag readback, readiness, and a healthy control journey. Resource and
queue signals must no longer worsen.

Failure adjudication is frozen:

- Cluster, DNS, TLS, telemetry, or transport loss that prevents observation is `infra_failed` and
  resumes only the affected trial.
- A successfully applied but undetected fault is `metric_fail`.
- A removed fault that remains unhealthy while telemetry is available is `metric_fail`.
- Cleanup or readback failure is `blocked` and quarantines the SUT.
- The destructive scenario phase executes once per candidate/environment cache key.

## 7. Ground-truth and locked-test isolation

Trust zones are `fw-sut`, `fw-baseline`, and the existing `fw-eval` zone with G02-specific service
accounts and NetworkPolicies.

The `faultwitness-eval` bucket uses these G02 prefixes:

```text
g02/scenarios/
g02/trials/
g02/ground-truth/
g02/locked-tests/
g02/evidence/
```

The G01 supplemental proof also probes existing `g01/traces/` without rewriting G01 evidence.

| Principal | Allowed | Denied |
| --- | --- | --- |
| `scenario-controller` | Read scenarios, write observations/trials, mutate the six flags | Ground truth, locked tests, product schemas, all other SUT mutations |
| `baseline-agent` | Read its observation, write its trial result, read metrics/logs/traces/health | Scenario spec, ground truth, locked tests, private evidence, `fw-eval` network access |
| `sealed-evaluator` | Read trials/GT/locked and write evidence | SUT mutation and baseline execution credentials |
| `ordinary-developer` | Read public documentation and preregistration | GT, locked, private trials/evidence, product schemas |

The live access target catalogue is six product schemas (`incident`, `runtime`, `checkpoint`,
`action`, `delivery`, `trace_buffer`), five G02 prefixes, and four observability endpoints
(Prometheus, Loki, Tempo, LangSmith). Each target has four probes: canonical owner control,
`baseline-agent`, `ordinary-developer`, and the target-specific controller/evaluator cross-boundary
probe, for 60 cells.

Controller, baseline, and evaluator image build contexts exclude ground truth, locked fixtures, and
the 160-row registry. The locked prefix may contain a no-answer deny sentinel but no G07 case data.

## 8. Baselines and scoring

All baselines consume the same immutable packet produced by one injection per seed.

1. Deterministic workflow uses fixed rules, no model, and no ground truth. It runs once per seed.
2. Naive ReAct uses `qwen3.7-plus-2026-05-26`, read-only observability tools, at most four model
   turns and six tool calls, and at most 8,000 input plus 1,024 output tokens per trial.
3. no-RAG uses one structured completion, no tools or retrieval, and at most 4,000 input plus 512
   output tokens per trial.

The two live baselines run three repetitions for each seed:

```text
32 cases × 3 repetitions × 2 baselines = 192 Gate trials
```

Iteration smoke uses two non-seed synthetic cases for both live baselines, for four nonoverlapping
trials. The Gate executor uses four workers. Each model attempt has one existing transient retry;
fallback model, channel, route, or family is prohibited.

Scoring is deterministic:

- Core E2E: correct Top-1 root cause, complete required evidence predicates, valid output/tool
  schemas, and no unsupported critical claim.
- Root-cause Top-3: normalized ground-truth cause is in the top three.
- Evidence precision: supported citations divided by all citations; no citations or malformed
  output scores zero.
- Unsupported critical claim: unsupported divided by all critical claims; missing/malformed
  diagnosis counts as one unsupported critical claim.
- Tool schema validity: valid applicable calls divided by all applicable calls; no-tool baselines
  report `N/A`.
- Dead/no-progress: repeated canonical tool+args with unchanged evidence digest, or exhausted
  budget without evidence progress.
- Family success: Core E2E macro average within each DSL family.

Each stochastic baseline first averages the three repetitions per case and then macro-averages 32
cases. `best baseline` is the largest Core E2E point estimate among the three baselines.

Confidence intervals use percentile bootstrap at 95%, cluster by case ID, retain repetitions within
the sampled case, use `B=2,000`, and seed the RNG from the dataset digest.

Valid but wrong, malformed, schema-invalid, or budget-exhausted outputs are scored failures and are
not rerun. DNS, TLS, transport, upstream-declared deadline, 429, or 5xx after the fixed retry is
`infra_failed` and only that trial resumes. The client does not kill a normally progressing trial
on a preset orchestration timeout. `fallback_count != 0` is a candidate failure.

## 9. Frozen quality floors

The following values are copied unchanged from the authoritative plan:

- Core E2E ≥ `max(70%, best baseline + 10pp)`
- Root-cause Top-3 ≥ 85%
- Evidence precision ≥ 90%
- Unsupported critical claim ≤ 2%
- Tool schema validity ≥ 99%
- Dead/no-progress loop < 1%
- Every fault family success ≥ 55%

G02 passes by proving the registry, measurement, and baseline comparison. Baselines are not required
to satisfy these future Agent floors.

## 10. Iterations

| Iteration | Scope boundary | Dependencies | Expected time | Falsifiable hypothesis | Owning L2 |
| --- | --- | --- | ---: | --- | --- |
| I-0016 Eval Protocol and Phase Engine | Manifest v2, phase DAG/cache, journal, CLI, double SHA, subject inheritance, reconciliation | Existing Eval tooling | 2h30 | An interruption after trial k resumes pending work without rewriting passed artifacts. | V-G02-002, V-G02-003, V-G02-016 |
| I-0017 Fault Lab and Scenario DSL | Pinned SUT, four families, six adapters, 32 seeds, Problem Brief, oracle | I-0016 phase interfaces | 4h00 | Four non-seed family smokes complete HEALTHY→FAULT_ACTIVE→HEALTHY with no flag drift. | V-G02-017 |
| I-0018 Sealed Registry and Isolation Evidence | Identities, namespaces, prefixes, 160-row registry, three G01 supplemental runners | I-0016, I-0017 contracts | 3h30 | Agent/developer cannot read GT/locked while evaluator can read them but cannot mutate SUT. | V-G02-010 |
| I-0019 Baselines and Scoring | Three baselines, packet, scorer, CI, usage/cost, live journal | I-0017, I-0018 | 4h30 | Four non-seed live trials score reproducibly and resume only the interrupted trial. | None; Gate work is L3 |
| I-0020 Unified Candidate Orchestration | Freeze one candidate and orchestrate existing runners only | I-0016–I-0019 | 0h30 excluding Gate Eval | Every phase completes without adding source, fixture, product behavior, or test framework. | No new L2 |

Every Iteration closes with `open_evidence: []`. L2 work is recorded as `owned_l2_ready`, not as
open Iteration evidence: its owner must already have implemented and unit-tested the runner,
negative fixture, phase interface, and candidate/environment binding protocol.

## 11. Environment compatibility retry rule

AMD-0003 removes the attempt-count and cumulative-time ceiling for external-tool, platform,
credential-transfer, infrastructure, and rollout work. Each attempt is persisted with candidate,
config, artifact, environment, timestamps, outcome, and attribution. A verified deterministic root
cause is corrected before another attempt; unchanged retries are allowed only for classified
transient infrastructure failures. Prior failures remain evidence and are never bulk-relabelled.

Unlimited attempts do not create an operator-adjudicated pass path. Metric failures, cleanup or
readback failures, authorization failures, digest drift, and zero-tolerance failures remain
blocking until their root cause is fixed and the normal runner passes. Paid trial sample counts,
per-attempt token ceilings, and the frozen internal transient retry are unchanged.

AMD-0004 additionally removes preset wall-clock kill timers from normally progressing G02 fetch,
transfer, import, rollout, Iteration Eval, and Gate phase execution. Elapsed time remains recorded
for budget reconciliation but cannot itself produce `infra_failed`, `metric_fail`, or cancellation.
A run ends only on pass, an explicit terminal failure, a verified no-progress condition with its
last progress evidence, or project-owner cancellation. Future Iteration and Gate plans use the same
rule. This is strictly an implementation-path change: validation N, the DSL's 90-second health
oracle windows, performance and quality metrics, paid token/cost budgets, retry statistics, and all
Gate pass criteria remain unchanged.

- K3s fallback: same-commit official minimal Docker Compose, selected before freeze.
- MinIO IAM fallback: digest-pinned stock `mc` job, otherwise block.
- SSH fallback: existing verified privileged channel/tunnel, otherwise block.
- Model fallback: retry only the failed infrastructure-failed trial through ModelGateway; no
  alternate model/channel and no change to the trial's internal retry budget.

## 12. Validation ownership

The authoritative machine-readable validation registry is
[`VALIDATIONS.yaml`](VALIDATIONS.yaml). It uniquely assigns every validation to L1, L2, or L3,
records both sample counts, the 3–5 audit, owning Iteration, runner, negative fixture, and artifact
paths. The registry is the source of truth for validation metadata; the complete human-readable
view is frozen below.

| ID | Validation and excluded failure | Layer and reason | Iter N | Gate N | 3–5 audit | Owner | Runner | Negative fixture | Artifact paths |
| --- | --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| V-G02-001 | Phase/DAG/resume; excludes repeated pass, lost trial, stale cache | L1; deterministic state fixtures | 5 | 0 | Reduced to five transitions | I-0016 | `g02.phase_contract` | `phase_stale_cache.json` | `EVAL-G02-001/artifacts/phase-contract.json` |
| V-G02-002 | Double SHA/binding; excludes false candidate and stale inheritance | L2; unified candidate only | 0 | 1 | One-time bootstrap | I-0016 | `g02.candidate_binding` | `candidate_non_evidence_descendant.json` | `EVAL-G02-005/.../preflight-candidate-binding/summary.json` |
| V-G02-003 | Manifest debt; excludes fail-late remote work | L2; full manifest set exists only at Gate | 0 | 13 | All 9 G01 + 4 G02 manifests required | I-0016 | `g02.manifest_debt` | `manifest_open_evidence.json` | `EVAL-G02-005/.../preflight-manifests/manifest-debt.json` |
| V-G02-004 | DSL/seed registry; excludes count and allocation drift | L1; closed schema/enumeration | 32 | 0 | All seeds are deliverables | I-0017 | `g02.dsl_registry` | `scenario_unknown_action.yaml` | `EVAL-G02-002/artifacts/seed-registry.json` |
| V-G02-005 | Six adapters/oracles; excludes missing state semantics | L1; category-exhaustive contracts | 6 | 0 | All six classes required | I-0017 | `g02.fault_oracle_contract` | `oracle_false_green.yaml` | `EVAL-G02-002/artifacts/fault-oracle-contract.json` |
| V-G02-006 | Live inject/detect/recover; excludes false green and restore drift | L3; family smoke then all seeds | 4 | 32 | Three would omit a family | I-0017 | `g02.scenario_matrix` | `fault_restore_noop.yaml` | Iteration smoke and Gate scenario summary |
| V-G02-007 | 160-row preregistry; excludes premature G07 materialization | L1; deterministic registry/object check | 160 | 0 | All rows are the deliverable | I-0018 | `g02.preregistry` | `prereg_materialized_case.yaml` | `EVAL-G02-003/artifacts/preregistry.json` |
| V-G02-008 | Package exclusion; excludes embedded GT/locked data | L1; digest-pinned content scan | 3 | 0 | Three images are exhaustive | I-0018 | `g02.sealed_package_scan` | `image_contains_ground_truth.txt` | `EVAL-G02-003/artifacts/sealed-package-scan.json` |
| V-G02-009 | Access matrix; excludes Agent/developer/evaluator/controller privilege drift | L3; four policy identities then 60 live cells | 4 | 60 | All four identities required | I-0018 | `g02.access_matrix` | `access_wrong_allow.yaml` | Iteration policy simulation and Gate matrix |
| V-G02-010 | G01 six-stage spans; excludes missing correlated stage evidence | L2; complete stack required | 0 | 6 | Six stages are exhaustive | I-0018 | `g02.stage_matrix` | `trace_missing_stage.json` | Gate six-stage matrix |
| V-G02-011 | G01 all-surface canary; excludes Secret/PII leakage | L3; four new writers then 22 live cells | 4 | 22 | All four writers required | I-0018 | `g02.canary_matrix` | `canary_leaked_artifact.json` | Iteration writer proof and Gate canary matrix |
| V-G02-012 | Scorer semantics; excludes mis-scored malformed/unsupported output | L1; pure algorithm | 5 | 0 | Five fixtures cover all branches | I-0019 | `g02.scorer_contract` | `score_unsupported_claim.json` | `EVAL-G02-004/artifacts/scorer-contract.json` |
| V-G02-013 | Seven thresholds; excludes omission or decrease | L1; exact constant registry | 7 | 0 | All seven values required | I-0019 | `g02.threshold_registry` | `threshold_decrease.yaml` | `EVAL-G02-004/artifacts/threshold-registry.json` |
| V-G02-014 | Deterministic baseline; excludes GT access and nondeterminism | L3; three behavior fixtures then 32 seeds | 3 | 32 | Correct/wrong/malformed are minimum | I-0019 | `g02.deterministic_baseline` | `deterministic_wrong_root.json` | Iteration smoke and Gate results |
| V-G02-015 | Live baseline/CI; excludes all-or-nothing retry and hidden fallback | L3; four runner smokes then 192 trials | 4 | 192 | Both runners need success and resume | I-0019 | `g02.live_baseline_matrix` | `journal_partial_transport.json` | Live smoke, journal index, aggregate metrics |
| V-G02-016 | Final reconciliation; excludes pending work and duplicate destructive run | L2; final candidate only | 0 | 1 | One-time reconciliation | I-0016 | `g02.reconciliation` | `reconciliation_pending.json` | Gate reconciliation summary |
| V-G02-017 | Clean-clone deployment; excludes dirty state and floating image | L2; candidate/environment bootstrap | 0 | 1 | One-time bootstrap | I-0017 | `g02.lab_bootstrap` | `lab_unpinned_image.yaml` | Gate lab-deploy summary |

The three G01 supplemental items are forward-recorded in [`CARRY_IN.yaml`](CARRY_IN.yaml). G01
REPORTs, manifests, CLAIMS, and tag history remain unchanged.

## 13. Gate Eval phases

All phases write `pending`, `running`, `pass`, `metric_fail`, `infra_failed`, `blocked`, plus UTC
start/end timestamps. A cache key contains candidate SHA, runtime/baseline image digests, SUT image
set, configuration, evaluator, dataset, and sanitized environment fingerprint.

| Phase | Depends on | Time | Destructive | Cache | Frozen adjudication |
| --- | --- | ---: | --- | --- | --- |
| `preflight-manifests` | None | 2m | No | Yes | Invalid schema, timestamps, set, or open evidence fails before remote work. |
| `preflight-candidate-binding` | manifests | 3m | No | Yes | Candidate, evidence head, or digest mismatch fails. |
| `preflight-static-inheritance` | binding | 8m | No | Yes | Compare L1 subject/image digests only; never rerun L1. Drift reopens its owner. |
| `preflight-upstream-g01` | static | 2m | No | Yes | Any debt in nine G01 manifests blocks remote phases. |
| `lab-deploy-and-bind` | G01 preflight | 12m | No | Yes | Clean-clone and pinned-image failure blocks; infrastructure loss is resumable. |
| `isolation-access-matrix` | lab deploy | 10m | No | Yes | All 60 allow/deny cells must match; any unauthorized success fails. |
| `trace-six-stage-matrix` | lab deploy | 8m | No | Yes | All six candidate-bound correlated stages must be present. |
| `all-surface-canary` | access, trace | 10m | No | Yes | Secret/PII hits must be zero; an unreadable surface is infrastructure failure, not a pass. |
| `scenario-matrix` | canary | 40m | **Yes** | **Once per exact key** | Applied-but-undetected and recovery failure are metric failures; cleanup failure quarantines and blocks. |
| `baseline-deterministic` | scenario | 2m | No | Yes | All 32 results must execute; wrong answers remain scored failures. |
| `baseline-live` | scenario, deterministic | 45m | No | Per trial | Persist 192 trials atomically; resume only infrastructure failures; fallback fails. |
| `baseline-aggregate` | both baselines | 3m | No | Yes | Produce estimates, CI, family, latency, token, cost, and failure reports. |
| `candidate-reconciliation` | aggregate | 5m | No | Yes | Pending, infrastructure failure, open evidence, drift, and repeated destructive work must be zero. |
| `close-readiness` | reconciliation | 3m | No | Yes | New runner, fixture, source, or framework changes reject closure and reopen the owner. |

The serial phase total is 153 minutes, or 2h33.
All values in the Time column and this total are estimates for planning and wall-time reconciliation,
not execution deadlines. Exceeding an estimate never changes a metric and never kills a phase.

CLI behavior is frozen:

- `--phase X` runs only X and fails if a dependency lacks valid cached evidence.
- Default follows DAG order and reuses exact-key passes.
- `--resume` skips passed work and continues pending/`infra_failed` trials.
- `--from-failed` begins at the earliest pending/`infra_failed` phase.
- `metric_fail` cannot be rerun on the same candidate to seek a favorable sample.

Each trial ID derives from candidate, dataset/config/evaluator digest, baseline, model, case ID, and
repetition. Raw journals live outside Git and under `g02/evidence/<phase-key>/`; Git stores sanitized
summaries and digests.

## 14. Manifest v2 and double-SHA protocol

The planned v2 manifest includes `candidate_sha`, runner-written `evaluated_revision`,
`evidence_head_sha`, subject digests, phase status/start/end/cache key, artifact digest/private URI,
environment fingerprint, commands, integrations, and `open_evidence`.

- Only the process that produced an artifact writes `evaluated_revision`.
- Evidence sync never bulk-replaces historical revisions.
- `candidate_sha` binds behavior, test/evaluator semantics, thresholds, workflows, dependencies,
  deployment, runtime images, dataset, and configuration.
- `evidence_head_sha` is the candidate or an allowlisted evidence/status-only descendant.
- Evidence-only changes with identical artifact digests do not redeploy.
- A semantic or runtime change reopens its owner. Unaffected phase evidence may be inherited only
  when its declared dependency closure and all digests remain identical; the original producing
  revision remains recorded.

The accepted details are in ADR-0009 and ADR-0013. I-0016 implements the mechanism; this planning
commit does not.

## 15. Gate pass criteria

G02 closes only when every criterion below passes:

1. V-G02-001: all five phase/resume fixtures pass without overwrite or trial loss.
2. V-G02-002: candidate, evidence head, image/config/evaluator/dataset/environment digests and
   inheritance are valid.
3. V-G02-003: all 13 manifests are valid, timestamped, and have no open evidence.
4. V-G02-004: exactly 32 executable seeds match the frozen family/difficulty/fault allocation.
5. V-G02-005: all six adapters implement inject, readback, UNKNOWN, recovery, and cleanup.
6. V-G02-006: all 32 seeds complete HEALTHY→FAULT_ACTIVE→HEALTHY on one candidate.
7. V-G02-007: the preregistry is exactly 160 rows with 80/40/40 splits and zero case objects.
8. V-G02-008: all three runtime images have zero GT, locked, registry, or canary findings.
9. V-G02-009: all 60 access cells match policy and unauthorized GT/locked access is zero.
10. V-G02-010: all six supplemental stages have complete, correlated, candidate-bound spans.
11. V-G02-011: all 22 Secret/PII surface cells have zero leakage.
12. V-G02-012: all five scorer fixtures produce their exact expected outcomes.
13. V-G02-013: all seven quality floors exactly equal the authoritative values.
14. V-G02-014: the deterministic baseline completes 32 seeds reproducibly without GT access.
15. V-G02-015: all 192 live trials complete or score, with no unresolved infrastructure failure or
    fallback, and produce 32-cluster 95% CIs, latency, token, CNY, family, and failure reports.
16. V-G02-016: pending, running, `infra_failed`, blocked, open evidence, digest drift, and duplicate
    destructive execution counts are zero; timestamps reconcile.
17. V-G02-017: clean-clone deployment uses only declared tools and linux/amd64 digest-pinned images.

Baseline attainment of the seven quality floors is not a G02 pass condition.

The closure asset set includes root/status documents (`AGENTS.md`, `PROJECT_STATE.yaml`, `README.md`,
`docs/roadmap/PHASES.md`) as well as the Gate report, governance records, ADR index, claims/status
assets, and next-Gate handoff. Lifecycle fields must agree. The Gate Report labels the three G01
supplemental artifacts without editing any closed G01 asset.

## 16. Human prerequisites

The project owner must:

1. Authorize destructive fault runs only in the private G02 SUT profile.
2. Confirm private-server/K3s, Bailian, and LangSmith credentials through the existing secret path.
3. Approve controller, baseline, evaluator, and developer-probe MinIO service accounts.
4. Confirm Bailian price, quota, and paid budget before I-0019 and Gate live phases.
5. Approve the OTel Demo commit, license, and image digest set.
6. Confirm reserved namespaces and prefixes contain no unrelated workload or object.

No NewAPI token, Online Boutique environment, or 160-case content is required.

## 17. Deliberate reductions

| Reduction | Reason |
| --- | --- |
| Do not materialize 160 cases | G07 owns actual cases. |
| One SUT | One demo supports all required families. |
| Exactly six faults | This is the minimum required fault-class coverage. |
| No third-party/custom chaos layer | flagd already provides the required injection surface. |
| One exact live model | G02 measures baselines, not multi-family routing. |
| Out-of-band baselines | Product Agent integration begins in G03. |
| No LLM judge or human agreement | Deterministic seed ground truth is sufficient. |
| No RAG, TrajectoryIR, or training | These belong to later Gates. |
| No soak/stability phase | G02 has no soak acceptance criterion. |
| No G01 production wall-time supplemental claim | Only the first three G01 evidence gaps are carry-in. |
| No NewAPI live route | It adds no required G02 evidence. |
| No baseline quality-floor certification | G02 freezes measurement and comparison only. |

## 18. Token and cost budget

| Work | Trials | Input cap | Output cap |
| --- | ---: | ---: | ---: |
| Gate Naive ReAct | 96 | 768,000 | 98,304 |
| Gate no-RAG | 96 | 384,000 | 49,152 |
| Iteration live smoke | 4 | 24,000 | 3,072 |
| **Total** | **196** | **1,176,000** | **150,528** |

Normal total is 1,326,528 tokens. Before candidate freeze, I-0019 records the actual account price.
At the 2026-07-23 China-region list rate of 2 CNY per million input tokens and 8 CNY per million
output tokens, the normal ceiling is 3.56 CNY. A complete one-retry contingency is 2,653,056 tokens
and 7.12 CNY. ModelGateway usage and the provider invoice are authoritative; a price or quota change
after freeze blocks the candidate rather than silently changing the route.
