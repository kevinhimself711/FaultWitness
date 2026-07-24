# Changelog

## Unreleased

### Governance maintenance

- Preserve I-0029/EVAL-G02-014 as terminal negative evidence after the private host's Python 3.8
  rejected `datetime.UTC`; plan I-0030 compatibility correction and I-0031/EVAL-G02-016 replacement.
- Activate I-0029 as the sole fourth replacement orchestration after I-0028 closed with byte-exact
  Windows transport evidence and no open evidence; I-0029 may only execute frozen Gate phases.
- Close I-0028 on candidate `09693ce` with EVAL-G02-013 passing 4/4 byte-exact transport cases,
  frozen validation N=4/0/4, zero remote/model execution, and no open evidence.
- Implement I-0028 byte-exact process transport with explicit UTF-8 bytes, binary subprocess I/O,
  explicit output decoding, and a real child-process LF-preservation regression.
- Activate I-0028 as the sole byte-exact transport corrective; I-0029 remains planned and no
  remote Gate L2, destructive, external-service, or model work is authorized during I-0028.
- Preserve I-0027/EVAL-G02-012 as terminal negative evidence after a real Windows subprocess probe
  proved text-mode LF-to-CRLF mutation before candidate binding; plan I-0028 byte-exact transport
  correction and I-0029/EVAL-G02-014 replacement without changing any Eval criterion.
- Activate I-0027 as the sole third replacement orchestration after I-0026 closed with bounded
  transport evidence and no open evidence; I-0027 may only execute the fourteen frozen phases.
- Close I-0026 on candidate `b50db66` with EVAL-G02-011 passing 4/4 bounded transport cases,
  frozen validation N=4/0/4, zero remote/model execution, and no open evidence.
- Implement I-0026 bounded privileged remote-script transport: upload script bytes through SSH
  stdin, execute through a short sudo path command, clean up deterministically, and ignore legacy
  wall-clock kill arguments without changing Eval criteria.
- Activate I-0026 as the sole bounded privileged remote-script transport corrective; I-0027 remains
  planned and no Gate L2, remote deployment, destructive scenario, external service, or model call is authorized.
- Record I-0025/EVAL-G02-010 as terminal failed after a deterministic Windows command-line length
  defect blocked the first access cell; plan I-0026 bounded transport correction and I-0027 replacement.
- Activate I-0025 as the sole replacement unified-candidate orchestration after I-0024 closed with
  executable frozen runners and no open evidence; I-0025 may not add implementation or framework.
- Activate I-0024 as the sole forward collector corrective; I-0025 remains planned and no Gate L2,
  destructive scenario, or model call is authorized during I-0024.
- Preserve terminal I-0023/EVAL-G02-008 after a deterministic runner-readiness failure; plan
  corrective I-0024 and replacement orchestration I-0025 without reopening I-0018/I-0023 or
  changing any validation N, threshold, locked asset, destructive rule, or model budget.
- Complete I-0022 without reopening I-0018 or I-0020; EVAL-G02-007 proves the exact observability
  correction and active-Iteration Eval routing with five deterministic cases and no Gate/model run.
- Activate I-0022 as the sole forward corrective; I-0020 stays terminal `failed` and I-0023 stays
  planned as the replacement orchestration.
- Preserve terminal EVAL-G02-005 after V-G02-009 proved two deterministic baseline observability
  denies; plan forward corrective I-0022 and replacement orchestration I-0023 without reopening
  I-0018 or I-0020, changing validation N, or starting any destructive/model phase.
- Accept AMD-0004: prohibit preset wall-clock kill timers for normally progressing G02 and future
  Iteration/Gate execution without changing any Eval or performance criterion.
- Accept AMD-0003: remove G02's three-attempt/45-minute infrastructure compatibility stop while
  retaining attributable failure history, fail-closed semantics, frozen paid-trial budgets, and all
  quality and zero-tolerance criteria.
- Record the G01 execution retrospective, six process badcases, and ADR-0009's accepted separation
  of behavior candidate and evidence-head revisions without rewriting any closed G01 evidence.
- Correct stale lifecycle surfaces after G01 closure and restore the authoritative G02 “Fault
  Laboratory and Baselines” placeholder boundary without starting G02 planning or implementation.
- Replace copied nine-path closure constants with an exact generated lifecycle/status asset set and
  make `verify-fast` reject AGENTS/README/PHASES drift from `PROJECT_STATE.yaml`.
- Remove the obsolete post-window `operator_adjudicated_pass` branch after `df644f1` established the
  fresh-session privileged-channel root cause; generic transport failures are blocking again.

### Gate closure

- Close G01 without waiver on immutable candidate `4c843553bad7a13023259d474e8fea1b8c174d40` and hand off to G02 in `not_started` state.
- Close G00 without waivers on immutable candidate `1f36a799c27dfe0709a529448e6935d0ea3103eb`.
- Hand off to G01 in `not_started` state; no G01 implementation is authorized before its Master Plan is frozen.

### Tooling

- Close I-0024 on candidate `a279703` and evidence commit `7e04d44` with five passing local
  readiness cases, unchanged 4/0/4 Iteration N, zero Gate L2/external/model execution, and
  `open_evidence: []`.
- Pass EVAL-G02-009 on candidate `a279703`: five deterministic collector-readiness cases preserve
  Iteration N=4/0/4, reject all named negatives, and execute zero Gate L2 cells, destructive work,
  external calls, or model calls.
- Add candidate/environment-bound G02 provisioning plus atomic resumable 60-cell, six-stage, and
  22-surface collectors; remove operator-precomputed phase inputs without changing any Gate N,
  threshold, isolation requirement, performance criterion, token budget, or failure semantics.
- Close I-0022 on candidate `7d6e07b` and evidence commit `7a42198`; retain EVAL-G02-005 as
  immutable failed history, redirect replacement Gate artifacts to EVAL-G02-008, and leave
  `open_evidence: []`.
- Pass EVAL-G02-007 with exact Prometheus/Loki/Tempo reachability, public-HTTPS private-range
  exclusion, four preserved identity denies, terminal-Eval rejection, and correct failed-transition
  attribution; external execution, Gate phases, and model calls remain zero.
- Close I-0021 on candidate `826453b` and evidence commit `fd4e1a0`; the machine policy now makes
  all post-epoch terminal Iteration records irreversible and leaves `open_evidence: []`.
- Pass EVAL-G02-006 on candidate `826453b`: all five forward-lifecycle cases, repository history
  scan, typed corrective links, and I-0020 owner-reopen absence pass with `open_evidence: []`.
- Enforce the I-0021 forward-only lifecycle policy in `verify-fast`: scan committed history and the
  worktree, reject terminal reactivation/deletion, require typed new Iterations and corrective
  links, and expose five deterministic EVAL-G02-006 cases without external execution.
- Close the final I-0017 corrective pass on business candidate `0d32648` and evidence commit
  `dae6702` with `open_evidence: []`; completed Iteration history is no longer eligible for
  reactivation.
- Pass the final I-0017 dual-SHA corrective Eval on candidate `0d32648`: validate the
  binding-declared evidence-head checkout guard, retain the unchanged N=32/N=6/N=4 evidence and
  image-set digest, restore all four live scenarios exactly, and leave `open_evidence: []` without
  a Gate scenario or model call.
- Make I-0017's lab deployment accept only the exact candidate or its binding-validated
  evidence-only descendant, resolving the post-candidate binding cycle without redeployment drift.
- Reopen owning I-0017 before I-0020 after readiness audit found lab deployment rejecting the
  validated evidence-only descendant required by the frozen dual-SHA Gate protocol.
- Close the corrective I-0019 owner pass on candidate `4bcc990` and evidence commit `5369c09` with
  direct Gate baseline interfaces ready, unchanged Iteration N=3/N=4, and `open_evidence: []`.
- Pass corrective EVAL-G02-004 on candidate `4bcc990`: retain exact N=3/N=4, use the frozen model
  with zero fallback, demonstrate trial-local interruption recovery, and close with 652/460 tokens,
  0.004984 CNY, and no open evidence.
- Reopen owning I-0019 before I-0020 after readiness audit found the three Gate baseline handlers
  importing precomputed JSON; replace that path with direct candidate-bound N=32/N=192 execution,
  atomic resumable live journals, sealed scoring, and the frozen clustered bootstrap interface.
- Complete the I-0017 corrective pass on candidate `c7d55f2`: redeploy 24/24 workloads, rerun the
  unchanged N=32 specification/N=6 adapter/N=4 live-family evidence, and prove both missing Gate
  handlers without executing the Gate N=32 live scenario matrix.
- Reopen owning I-0017 before I-0020 after readiness audit found registered but unmapped
  `lab-deploy-and-bind` and `scenario-matrix` phases; add candidate/image-bound deployment and
  atomic 32-seed continuation interfaces without executing Gate-layer N=32 work.
- Complete I-0019 live evidence on candidate `c4fa561`: pass five scorer branches, seven exact
  quality floors, deterministic N=3, and four exact-model non-seed live trials with zero fallback,
  atomic trial-local resume, 652/447 tokens, 0.00488 CNY, and no open evidence.
- Preserve superseded candidate `b448c5c` as a harness failure: strict schema enforcement caught the
  `evidence_ids` alias that the first validator accepted; fix the root cause and rerun on a new
  candidate without changing N, thresholds, token caps, or retry semantics.
- Activate I-0019 and add the shared observation-packet boundary, exact three-baseline registry,
  deterministic scorer, frozen seven-value threshold registry, clustered 2,000-resample bootstrap,
  attributable CNY usage accounting, exact-route Bailian adapter, and atomic trial-local resume.
- Remove preset orchestration kill time from the G02 paid baseline adapter while retaining the
  frozen model, N, quality/performance metrics, token/cost ceilings, and one internal transient retry.
- Complete I-0018 on immutable implementation candidate `bcc6437`: pass the 160-row metadata-only
  preregistry, three sealed package scans, four identity policies, namespace isolation, four writer
  canaries, and owned Gate runner contracts with no model calls or open evidence.
- Complete I-0017 on immutable implementation candidate `ca9de48`: pass all 32 seed
  specifications, six adapter/oracle contracts, and four candidate-bound live family smokes with
  exact restoration, no core-case materialization, no model calls, and no open evidence.
- Implement the I-0017 digest-pinned K3s lab bootstrap, deterministic 32-seed Scenario DSL,
  six allowlisted flag adapters, ternary fault/recovery oracles, exact restoration, and registered
  false-green, restore-noop, unknown-action, and unpinned-image negative paths.
- Complete I-0016 on immutable implementation candidate `a4c242b`: pass five deterministic phase,
  cache, resume, continuation, and destructive run-once cases; prove readiness of the owned
  candidate-binding, manifest-debt, and reconciliation L2 runners without executing Gate L2 work.
- Complete I-0015 on immutable candidate `4c84355`: pass public Ubuntu/Windows/audit
  checks, the clean 15-minute readiness window, 14/14 walkthroughs, 36/36 live
  model trials, recovery/rollback, PostgreSQL/Redis/Trace/API failure matrices,
  and final six-binding/three-migration reconciliation with zero durable backlog.
- Land real I-0015 recovery and failure evidence: embedded-etcd restore,
  project-only Helm rollback/reinstall, 82-transition PostgreSQL atomicity,
  duplicate/crash/fencing checks, Redis pending recovery, uncertain-ACK
  LangSmith replay, and production-store 10,000-event/100-reconnect API/SSE load;
  pass cold-JWKS Keycloak outage fail-closed with service recovery; retain final
  same-SHA binding, policy/canary, supply-chain, and close-readiness as open.
- Pass private durable reconciliation with six exact candidate bindings, three migrations, and zero DLQ/Outbox/stale-lease/Trace backlog; pass fresh-target PostgreSQL restore with exact schema/data digest equality; and pass all three public required checks on PR `#18` audit-head `72aff8f` while retaining final same-SHA binding as open.
- Redeploy audit candidate `16294bc` across every private G01 component and pass candidate-bound platform/schema, OIDC API, sanitized Trace, Model Gateway, four-runtime, five-case network, and Docker-coexistence checks; retain unresolved public and deep recovery evidence.
- Extend I-0015 to 220 passing tests with 10,000-event/100-reconnect SSE coverage, 10,000-delivery/100-crash atomicity and dedupe reference matrices, fail-closed upstream-Eval debt checks, and exact G01 closure-boundary enforcement; retain private integration, replay, recovery, and public candidate binding as open.
- Add the candidate-bound G01 audit and close-readiness commands on `bc8c040a`, pass 210 local tests and the private deployment/runtime/network/service checkpoint, and retain all unresolved failure-matrix, cross-platform, replay, reconciliation, restore, rollback, and closure evidence as explicit I-0015 debt.
- Deploy the authenticated private Model Gateway checkpoint from candidate `18ff0c1`: observe `1/1 Ready` ClusterIP service and pass a real Keycloak OIDC-to-Bailian Qwen smoke with exact route and attributed usage; retain all EVAL-G01-009 full-candidate work as open.
- Add the private candidate-bound Model Gateway service and deployment path: strict OIDC-derived tenant context, identity-injection denial, non-root read-only ClusterIP workload, repository-external Bailian secret handoff, exact catalog packaging, authenticated live smoke, and complete runtime dependency locking.
- Complete I-0014 and EVAL-G01-008 on candidate `21c2a96`: pass 36/36 live Bailian trials across Qwen, DeepSeek, and GLM complete/structured/forced-tool/stream capabilities, the controlled NewAPI wire matrix, attributed usage, and one sanitized LangSmith Trace per trial; retain the single-live-upstream limitation and activate I-0015.
- Implement the I-0014 ModelGateway foundation: a versioned three-family capability and route catalog, shared Bailian/NewAPI-compatible adapter, strict structured and forced-tool validation, deterministic streaming and usage attribution, bounded retry/repair/pre-output fallback, post-first-chunk partial failure, offline wire tests, and a candidate-bound 36-trial live Eval entry point.
- Complete the I-0013 implementation checkpoint on candidate `ae0a3be`: deploy migration `003_i0013` and the private Trace Service, pass live sanitized LangSmith/OTLP/archive delivery with zero pending traces, retain the complete outage/canary/correlation/latency matrix as Gate debt, and activate I-0014.
- Implement the I-0013 sanitized Trace foundation: strict pre-persistence allowlisting, irreversible tenant/correlation references, encrypted bounded PostgreSQL delivery state, deterministic LangSmith/OTLP replay, correlated Tempo/Loki/Prometheus signals, private MinIO/DVC manifests, and a candidate-bound private Trace Service deployment path.
- Complete the I-0012 implementation checkpoint on candidate `5a1b607`: deploy the private candidate-bound Control API and Keycloak realm, pass live OIDC create/read/SSE and tenant/role/approval denial smoke, retain the full EVAL-G01-006 conformance/load matrix as Gate debt, and activate I-0013.
- Implement the I-0012 authenticated Control API foundation: eight frozen FastAPI paths, fail-closed RS256 OIDC tenant derivation, role and cross-tenant denial, PostgreSQL Incident/idempotency/event projection, exact replay cursors, typed retention/backpressure SSE controls, and truthful empty capability/approval behavior.
- Add a candidate-bound, non-root, private-ClusterIP Control API image and K3s deployment path with locked dependencies and explicit network policy.
- Add candidate-bound Keycloak realm provisioning for two synthetic tenants, four roles, a mapped API audience/tenant claim, and eight out-of-band credentialed users.
- Complete the I-0011 implementation checkpoint on candidate `4844961`: add owner-isolated PostgreSQL state/idempotency/outbox/inbox/DLQ, Redis Streams recovery, fenced AES-GCM checkpoints, and deploy migration `001_i0011` with 17 observed runtime tables; retain the complete EVAL-G01-005 fault matrix as Gate debt and activate I-0012.
- Pass the Windows EVAL-G01-004 conformance run on candidate `f81c7f0` with 82 deterministic legal transitions and 492 rejected mutations; retain cross-platform digest and public compatibility evidence for the final candidate, and activate I-0011 durable state work.
- Compile the nine frozen G00 contract sources into a byte-stable 1.1.0 package resource; add 21 strict core models, 12 G01 support models, and a deterministic four-owner kernel that executes all 82 transitions with explicit predicates and fail-closed version, fencing, digest, idempotency, terminal-state, and private-reasoning boundaries.
- Deploy all eleven I-0009 data, identity, policy, storage, and observability workloads from candidate `0c8b66c`, with private out-of-band Secrets, linux/amd64 digest pins, deterministic bundle binding, and sanitized Ready inventory; retain the full EVAL-G01-003 matrix as candidate debt and activate I-0010.
- Document the I-0009 platform-services deployment, isolation, restore, observability, supply-chain, failure, and public/private evidence contract while keeping implementation, private deployment, and EVAL-G01-003 explicitly pending.
- Hand off the landed I-0008 infrastructure implementation to I-0009 while retaining EVAL-G01-002 as explicit blocking candidate debt; activate only the frozen platform-service and operational-observability scope.
- Land the I-0008 infrastructure checkpoint: pinned K3s/Helm deployment assets, gVisor/Kata/NVIDIA runtime integration, offline image handling, runtime and network smoke definitions, Docker coexistence auditing, diagnostics, and focused tests. The private K3s service and required runtimes are deployed; I-0008 remains open without an EVAL-G01-002 pass claim.
- Add I-0007 SOPS/Age encrypted handoff migration, project identity bootstrap, fail-closed host pinning, operator-approved long-lived credential acceptance, read-only host probing, and private Eval commands.
- Correct I-0007's risk premise: untracked owner-host handoff values are retained unchanged when publication/history scans show zero exposure; confirmed compromise or operator revocation remains the rotation trigger.
- Replace the non-executable Windows SSH askpass batch helper with a repository-source-digest-locked native helper, dummy-value self-test, and redacted authentication failure categories.
- Complete I-0007 on candidate `7a9237c4c5b9fc0c736435e836534e72712c4169` with exact handoff deletion/ignore, pinned dedicated SSH access, two matching sanitized capability probes, and waiver-free EVAL-G01-001.
- Activate I-0008 for the frozen project-owned K3s, isolated runtime, GPU, coexistence, and rollback scope; no server mutation is included in the activation commit.
- Pin and checksum SOPS 3.13.2 and Age 1.3.1, validate their public configuration with JSON Schema, and keep all private stores outside the repository.
- Extend publication scanning to PowerShell/shell assets and LangSmith token shapes with negative tests.
- Pin the Python, Node.js, uv, and pnpm repository toolchains.
- Add locked Python and Node workspaces and cross-platform verification entry points.
- Record the I-0001 iteration and EVAL-G00-001 evidence assets.
- Add versioned governance schemas, the canonical repository CLI, negative policy tests, and cross-platform baseline CI.
- Activate the reviewed `main` Ruleset and record the owner-approved public-visibility amendment.
- Make changed-asset evaluation infer the active completed Iteration while ignoring planned bootstrap records.

### Planning

- Activate I-0023 as the sole replacement unified-candidate orchestration after I-0022 closed; it
  may only bind and execute the fourteen frozen phases under EVAL-G02-008.
- Activate I-0020 as the sole unified-candidate orchestration Iteration after I-0021 closed; no new
  runner, fixture, product behavior, test framework, threshold, or Gate phase is authorized.
- Activate I-0021 as the sole forward governance corrective before I-0020; it may change only
  lifecycle governance, deterministic checks, tests, and evidence.
- Plan forward corrective I-0021 to make completed/failed Iteration records machine-immutable,
  remove owner-reopen semantics, and freeze Gate preflight/failure classification before I-0020.
- Activate I-0017 as the sole G02 Iteration authorized for the pinned fault lab, Scenario DSL,
  32-seed catalogue, oracle, exact restoration, and clean-clone runner scope.
- Activate I-0007 as the sole G01 Iteration authorized for secure bootstrap and sanitized read-only capability evidence.
- Freeze the decision-complete G01 Master Plan with nine implementation Iterations, nine pre-registered Evals, fourteen failure walkthroughs, and immutable no-waiver closure criteria.
- Record a host-coexisting single-node K3s topology that protects existing Docker workloads and exposes no public control plane.
- Correct the model topology to three live model families through Bailian plus a NewAPI-compatible channel, without claiming three independent providers.
- Retain LangSmith as the required Agent/Eval trace backend and record its credential as available but unused until secure bootstrap I-0007.
- Freeze the architecture-first final project blueprint.
- Freeze the decision-complete G00 Gate Master Plan.
- Establish the initial project state and repository collaboration rules.
- Catalog the complete JD and interview corpus without publishing raw third-party material.
- Establish 57 evidence-backed requirements with role, architecture-plane, Gate, and verification mappings.
- Add fail-closed evidence quality and exact-coverage validation for the requirement registry.
- Freeze five linked architecture views, component/data ownership, trust boundaries, and failure walkthroughs.
- Add the initial Threat Model and accepted decisions for planes, outbox, trace/eval, artifacts, delivery, and Action safety.
- Freeze four machine-readable state machines and deterministically validated Mermaid views.
- Add OpenAPI 3.1, AsyncAPI 3.0, core type, Command/Event, error, and fixed failure contracts.
- Enforce reachability, terminal convergence, R2 approval, uncertainty, fencing, identity, idempotency, and version semantics.
- Add fail-closed secret, publication, dependency-license, source-ownership, Action-pin, lockfile, and CycloneDX SBOM audits.
- Add pinned browser rendering for every Mermaid diagram and a required Ubuntu audit status check.
- Materialize fourteen frozen G00 design walkthroughs plus PR, Issue, external-link, and evidence-sync governance.
- Complete I-0006 on immutable candidate `42b9708` with three required public checks and preserved SBOM evidence.
- Reopen I-0006 to correct the frozen `not_started` G01 handoff state found by full Gate readiness review.
- Complete the I-0006 handoff correction on immutable candidate `b1bc316` with 43 tests and three required checks.
- Reopen I-0006 to add fail-closed machine validation for full G00 closure readiness.
- Complete I-0006 closure-readiness enforcement on immutable candidate `b6d5f4d` with 48 tests.
- Reopen I-0006 to enforce the exact no-Iteration G00 closure asset boundary.
- Complete I-0006 closure-protocol enforcement on immutable candidate `c38ca79` with 51 tests.

No product implementation, deployment, secret migration, live model call, or LangSmith trace is included in this planning baseline.
