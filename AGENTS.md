---
active_gate: G03
active_gate_status: not_started
active_iteration: null
next_iteration: null
last_closed_gate: G02
---

# FaultWitness Repository Instructions

## Mission and current phase

FaultWitness is a multi-tenant Agent Runtime for investigating microservice incidents, proposing bounded remediations, executing approved actions, and producing auditable evaluation and training assets.

G00, G01, and G02 are closed without waiver. EVAL-G02-046 passed fourteen phases, 32 executable
fault scenarios, 60/6/22 safety and observability matrices, deterministic N=32, live-model N=192,
clustered 95% bootstrap aggregation, reconciliation, and close-readiness with no open evidence.
G03 is `not_started`; its placeholder authorizes planning only. A decision-complete G03 Master Plan
must be frozen before any G03 implementation begins. Historical failed and completed G02 records
remain immutable, but their high-overhead lifecycle ceremony is not a template for future debugging.

## Source-of-truth order

When artifacts disagree, use this precedence and stop to resolve the drift instead of silently choosing one:

1. The authoritative final project plan.
2. The active Gate plan and accepted ADRs.
3. Versioned public contracts and machine-readable state-machine specifications.
4. Tests and implementation.
5. Generated reports and explanatory documentation.

PROJECT_STATE.yaml is the authority for the active Gate and work item, not for architecture semantics.

## Required workflow

- Planned feature work begins from a bounded Iteration in the active Gate Master Plan. A defect
  discovered while executing an existing runner may be fixed directly without creating a new
  corrective/attempt lifecycle when the change is minimal, preserves frozen semantics, uses the
  existing targeted test or real seam, and reruns only affected trials and real dependencies.
- Do not create planning, activation, evidence-head, or closure commits around a small debug fix.
  Record the root cause, changed semantic branch, targeted verification, and affected replay once
  in the final Gate/release report.
- A Gate Master Plan must be frozen before its implementation iterations start.
- Historical `I-*`, `C-G##-*`, and `A-G##-*` identifiers remain immutable audit records. They do not
  require future Gates to reproduce the G02 corrective/attempt state machine.
- A debug fix owns one verified root cause, changes only its semantic branch, uses the existing test
  entrypoint, and adds no bespoke Eval framework. Gate Report synchronization is deferred to closure.
- Gate execution is an experiment sequence, not a separate mandatory work-item lifecycle. Existing
  runner repairs are allowed under the short-loop rule above; new product scope or a substantial new
  framework still returns to a planned Iteration.
- Governance and status documents may be amended during a Gate attempt when a provenance rule
  blocks execution without protecting product behavior, Eval semantics, or an experimental
  subject. Such amendments remain evidence-only, do not create a new business candidate, and must
  not be expanded into another lifecycle or activation sequence.
- Report corrective engineering, targeted corrective verification, Gate-attempt execution, and
  governance migration/closure as separate cost classes. Duration estimates never kill execution.
- Behavioral changes, affected tests, documentation, and version manifests belong in the same commit.
- Do not lower a Gate threshold, modify locked tests, or alter ground truth in an implementation commit.
- Failed Gates, negative experiments, and rejected architectures must remain in the repository history.
- Gate closure is a separate asset-only commit evaluated against an immutable candidate SHA.
- Final Gate execution may repair a defect in an existing runner under the short-loop rule, but may
  not add product scope or a substantial Eval framework. The changed branch and affected dependency
  closure must pass before execution continues; completed historical records are never reopened.
- Expensive Evals must be decomposed into attributable phases whose immutable results are
  keyed by code candidate, runtime artifact/config digests, and environment fingerprint.
- Eval runners that invoke destructive, long-running, or external-service work must support
  phase selection and continuation from failed or pending work before the Gate run begins.
- Manifest debt, candidate bindings, schemas, publication checks, and other deterministic
  preconditions must pass before any soak, recovery rehearsal, or paid live matrix starts.
- A stability window runs once for an unchanged runtime artifact and environment fingerprint.
  Its stage-specific failure semantics must be frozen before execution; later unrelated checks
  consume its evidence instead of rerunning it.
- Gate walkthroughs aggregate immutable phase evidence and must not silently re-execute the
  same remote smoke, load, recovery, or model trial.
- All Eval harnesses, negative fixtures, and close-readiness fixtures must pass before the
  business candidate is frozen.
- Candidate-bound evaluation uses the accepted two-SHA model: `candidate_sha` identifies
  behavior and runtime artifacts, while `evidence_head_sha` identifies an asset-only descendant.
  Any behavior, test-semantic, threshold, workflow, or runtime-artifact change creates a new
  candidate; evidence-only changes do not.
- A frozen `candidate_sha` is an explicit evaluation input. Current branch HEAD, the newest commit,
  and the commit containing a report are not alternate authorities for the business candidate.
  Exact `HEAD == candidate_sha` is required only when a runner is explicitly evaluating the
  candidate checkout itself. A runner operating from a validated evidence-only descendant must
  prove ancestry, changed-path allowlisting, and unchanged subject digests instead of rebinding or
  redeploying the candidate.
- When the orchestration worktree has advanced only for governance or evidence, candidate-bound
  execution may run directly from that descendant after ancestry, changed-path scope, and every
  phase-owned runtime/Eval subject digest are verified. Use a clean detached checkout only when the
  current worktree contains uncommitted or non-allowlisted subject changes. Do not switch worktrees,
  rewrite a binding, or create another commit merely to make orchestration HEAD equal the candidate.
  Generated phase artifacts never become runtime inputs.
- No tracked artifact may be required to contain the SHA of the commit that contains that artifact.
  A runner records the already-existing execution checkpoint it observed before producing output;
  the later evidence/closure commit is identified by Git history or its Gate tag and does not
  rewrite the producing revision to chase its own SHA.
- Completed work-item records are immutable. A later defect is fixed forward and linked in the final
  report; it never changes the completed record back to `in_progress`. A separate corrective record
  is optional and justified only when the work is large enough to need an independently planned scope.
- `verify-fast` scans every work-item transition from the machine policy epoch as well as the
  current worktree. It rejects terminal-record deletion/reactivation even when a later commit hides
  the regression. New C/A records use their dedicated namespace; legacy I correctives retain their
  same-Gate terminal links through the machine-readable legacy registry.
- Candidate readiness is the deterministic front of Gate Eval, not a separate open-ended audit.
  Transient infrastructure failures resume the same phase/trial. A deterministic failure blocks
  progress until its root cause is fixed; then only the failed branch and affected dependencies rerun.
- SHA and evidence-inheritance rules are provenance controls only. They must not alter Eval N,
  locked tests, Ground Truth, quality or performance thresholds, health-oracle windows, token/cost
  ceilings, or failure semantics.
- Before complying with a governance-only failure, apply an information-gain check. If satisfying
  it would only add state mirrors, prose, commit ordering, or SHA churn while leaving all runtime
  and Eval subjects unchanged, remove or bypass that governance requirement through the smallest
  reviewable amendment. A second consecutive governance action without advancing a real phase or
  trial is an execution-deadlock signal, not a reason to add another governance step.
- Gate closure must update the controlled root/status asset set, including `AGENTS.md`,
  `PROJECT_STATE.yaml`, `README.md`, and `docs/roadmap/PHASES.md`, and their lifecycle fields
  must agree before verification passes.
- Live external-service matrices must persist each trial atomically and resume only failed or
  pending trials. A single attributable transport failure must not discard completed trials.
- Once a failure has a verified root cause, no generic operator-adjudicated pass path may remain;
  the root cause is fixed and the affected phase is rerun under its normal blocking semantics.
- Cross-platform stdin transport for SSH, credentials, scripts, and structured payloads must use
  explicit bytes and explicit decoding. A mock runner is insufficient for byte-integrity claims:
  the owning corrective must exercise a real child process on the affected platform and compare
  the received bytes before any remote Gate phase may resume.
- A runner shipped to a remote or sealed environment must execute its import and minimum runtime
  path under that environment's actual interpreter version before its owning Iteration closes.
  Local current-version imports and syntax-only checks are insufficient compatibility evidence.
- A correction that changes an external client command, platform boundary, credential transport,
  image path, interpreter path, or protocol seam must exercise the changed operation once through
  the real tool/environment before the corrective closes. This is targeted seam evidence, not a
  full Gate matrix and not permission to increase the corrective sample.
- A correction that changes ambient traffic, load generation, or other workload supply must list
  every oracle branch that depends on that supply as affected. Before the corrective closes, each
  distinct request protocol it changes receives one deterministic real-seam proof; readiness and a
  no-fault smoke alone cannot stand in for a fault-producing workload input.
- Every future Master Plan Iteration declares each external client/platform/credential/image/
  interpreter/protocol operation it introduces, plus a real-seam runner, a predeclared read-only
  failure diagnostic, and an artifact path. A memory backend, mock, schema check, or matrix-shape
  test cannot be the sole readiness evidence for a live Gate operation.
- Gate attempts use only frozen diagnostic runners and command templates. Ad hoc diagnostic tools
  or command-construction experiments are implementation work and require a new corrective; each
  failed attempt records diagnostic invocation and command-error counts in its failure artifact.
- Every digest-pinned helper or probe image required after lab deployment must enter the same
  digest-verified offline staging and containerd-import path as the SUT images. A later in-cluster
  registry pull is not candidate bootstrap evidence and may not be assumed available.
- Do not commit or push unless the user explicitly requests it.

Planning-only commits may create or refine future work-item and Eval assets without activating them. They never authorize product behavior, infrastructure mutation, credential use, or live evaluation.

## Validation ownership and Eval execution

- Every validation item belongs to exactly one layer:
  - L1 (Iteration-only proof) is deterministic, closed, has no external dependency, and proves a
    correctness property introduced by its owning Iteration. Gate evaluation verifies inheritance
    digests and does not rerun it.
  - L2 (unified-candidate-only proof) requires the frozen candidate and complete stack, is
    statistical, soak, stress, destructive, live-external, or cross-Iteration end to end. It does
    not run during its owning Iteration.
  - L3 (layered revalidation) uses the smallest sufficient Iteration sample and a strictly larger,
    different Gate sample to prove scale or consistency on the unified candidate.
- The same validation may not run at both layers with the same N. If equal N is the only meaningful
  design, classify it as L2 and do not run it in the Iteration.
- Every L2 item names an owning Iteration. That Iteration implements and unit-tests the runner,
  negative fixture, and phase interface before it closes. Final Gate execution may make a minimal
  repair to that existing runner under the short-loop rule, but may not introduce a new framework,
  fixture family, metric, threshold, or sample design.
- An Iteration that adds a persistence surface, egress surface, trace stage, identity principal, or
  storage namespace proves the new surface's leakage, authorization, and observability properties
  in that same Iteration.
- An Iteration closes only with `open_evidence: []`. Evidence that cannot be completed there must be
  reclassified before closure; it is never rolled forward from a completed Iteration.
- Eval phases run in information-per-time order. Manifest debt, candidate binding, schemas, static
  inheritance, and upstream debt must pass before remote, destructive, soak, or paid work.
- Live and multi-trial matrices persist every trial atomically and resume only pending or
  infrastructure-failed trials. A transport failure never invalidates completed trials.
- A runner that uses a deterministic external identity must either derive the complete submitted
  payload deterministically or persist a nonce before the first side effect. It must journal the
  side-effect checkpoint before any later relay, collection, or aggregation step can fail; replaying
  the same identity with different content is a runner defect, never an operator-adjudicated pass.
- A destructive or soak phase runs once for an unchanged candidate/artifact/config/environment key.
  Its pass, threshold-fail, infrastructure-fail, cleanup, and attribution semantics are frozen in
  the Master Plan before execution.
- Every phase manifest records start and end timestamps. Only the run that produced an artifact may
  write `evaluated_revision`; evidence synchronization must not bulk-replace it.
- Candidate evaluation uses separate `candidate_sha` and evidence-only `evidence_head_sha` under
  ADR-0009 and ADR-0013. Evidence-only descendants never impersonate a new runtime candidate.
- After a failure has a verified root cause, no operator-adjudicated pass route may remain. Fix the
  cause and rerun under the phase's normal blocking semantics.
- Environment compatibility, rollout, credential-transfer, and external-tool attempts have no
  attempt-count or cumulative-time ceiling. Every attempt must remain attributable. Correct a known
  deterministic root cause before retrying; retry unchanged work only for a classified transient
  infrastructure failure. Unlimited retries never convert metric, policy, cleanup, digest, or
  zero-tolerance failures into a pass.
- A normally progressing infrastructure operation, Iteration Eval, Gate phase, rollout, transfer,
  or external-tool execution must not be killed or failed by a preset wall-clock timeout. Duration
  estimates are observability and planning data only. Stop only on an explicit terminal result, a
  classified deterministic failure, verified loss of progress, or project-owner cancellation.
  This orchestration rule never changes Eval samples, quality or performance thresholds, health
  oracle windows, token/cost ceilings, retry statistics, or Gate pass criteria.
- Every zero-tolerance criterion has a named runner, a negative fixture, and a reviewable artifact
  path in a machine-validated registry. A missing field invalidates the criterion.

## Architecture invariants

- Incident, Runtime Task, Agent Graph, and ActionTransaction are separate state machines with separate owners.
- Components communicate across ownership boundaries through typed commands and transactional outbox events.
- Tenant identity comes from authenticated context and cannot be supplied or overridden by request bodies.
- The Agent can propose ToolCall and ActionProposal objects but cannot execute arbitrary shell commands or write directly to Kubernetes.
- Action Executor is the only write boundary and must enforce policy, approval, idempotency, postconditions, and compensation.
- R2 actions cannot execute without a valid immutable approval digest.
- At-least-once task delivery must be paired with idempotent external actions; never claim distributed exactly-once execution.
- UNCERTAIN action outcomes cannot be retried blindly.
- Ground truth and locked evaluation data are never accessible to the Agent runtime.
- Do not store or expose private model chain of thought. Store structured summaries, evidence references, tool events, and state deltas only.

Changes to these invariants require an ADR, an architecture version update, migration and replay analysis, and targeted regression tests before implementation.

## Evidence and documentation rules

- Raw job descriptions, interview notes, restricted documents, secrets, and private traces must not be committed.
- Public requirements may contain source IDs and paraphrases, not copied source bodies.
- Tier-C coaching answers cannot be the sole evidence for a mandatory requirement or metric.
- Every public claim must eventually map to code, tests, trace or dataset evidence, and a reproducible evaluation.
- Code, APIs, schemas, identifiers, and code comments are English.
- AGENTS.md is English. Design, evaluation, and retrospective documents are primarily Chinese with English technical identifiers.

## Commands

The governance CLI is established. The canonical entry point is:

    uv run python -m faultwitness_dev <command>

Makefile targets may wrap the canonical command on Linux but must not become the source of truth.

## Safety

- Never commit credentials or decrypted secret files.
- Never run privileged server, chaos, sandbox, or remediation commands unless the active iteration explicitly authorizes the exact environment and test.
- Public CI must never receive privileged server, Kubernetes administrator, model-provider, or production-like secrets.
- Never overwrite an existing remote repository or reuse an unexpected directory when bootstrapping.
