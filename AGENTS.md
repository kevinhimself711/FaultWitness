---
active_gate: G02
active_gate_status: in_progress
active_iteration: null
next_iteration: A-G02-001
last_closed_gate: G01
---

# FaultWitness Repository Instructions

## Mission and current phase

FaultWitness is a multi-tenant Agent Runtime for investigating microservice incidents, proposing bounded remediations, executing approved actions, and producing auditable evaluation and training assets.

G00 and G01 are closed. G02 is `in_progress`. I-0016 through I-0019 and forward correctives I-0021,
I-0022, I-0024, I-0026, I-0028, I-0030, I-0032, and I-0034 are completed with no open evidence. I-0020,
I-0023, I-0025, I-0027, I-0029, I-0031, I-0033, and I-0035 are terminally failed with complete
negative evidence. Legacy I-0036/I-0037 were retired before implementation when work-item
namespaces were separated. C-G02-001 is completed with targeted real-client evidence and no open
evidence; A-G02-001 is the separate next Gate attempt. No terminal work item may be reopened.

## Source-of-truth order

When artifacts disagree, use this precedence and stop to resolve the drift instead of silently choosing one:

1. The authoritative final project plan.
2. The active Gate plan and accepted ADRs.
3. Versioned public contracts and machine-readable state-machine specifications.
4. Tests and implementation.
5. Generated reports and explanatory documentation.

PROJECT_STATE.yaml is the authority for the active Gate and work item, not for architecture semantics.

## Required workflow

- No behavioral change may begin without a planned `I-####` or `C-G##-###` work-item plan.
- A Gate Master Plan must be frozen before its implementation iterations start.
- `I-####` is reserved for Iterations frozen before Gate execution. Execution-time root-cause work
  uses `C-G##-###`; a unified-candidate Gate run uses `A-G##-###`. Never continue the planned
  Iteration sequence to disguise emergent corrective work or a Gate retry.
- A corrective owns exactly one named root cause. It includes only the fix, changed semantic
  branches, any required minimum real-seam proof, and its own evidence. It executes no Gate L2 or full
  Gate Eval, reuses the existing test entrypoint, adds no bespoke per-corrective Eval harness, and
  defers Master Plan, Validation-final-path, Claims, and Gate Report synchronization to the
  Gate-attempt or closure boundary. Engineering, targeted verification, Gate execution, and
  governance synchronization are accounted separately.
- A Gate attempt is not an Iteration and is not corrective engineering cost. It may only orchestrate
  frozen runners and evidence; `src/`, `deploy/`, `tests/`, `config/`, and `schemas/` changes are
  forbidden while an `A-G##-###` work item is active.
- Report corrective engineering, targeted corrective verification, Gate-attempt execution, and
  governance migration/closure as separate cost classes. Duration estimates never kill execution.
- Behavioral changes, affected tests, documentation, and version manifests belong in the same commit.
- Do not lower a Gate threshold, modify locked tests, or alter ground truth in an implementation commit.
- Failed Gates, negative experiments, and rejected architectures must remain in the repository history.
- Gate closure is a separate asset-only commit evaluated against an immutable candidate SHA.
- A final `A-G##-###` Gate attempt may only orchestrate frozen checks, reverify one candidate,
  and synchronize evidence. It may not add product behavior or a substantial Eval framework;
  missing owning-runner work creates a new forward `C-G##-###` assigned to that domain and produces
  a new candidate; a completed work-item record is not reopened.
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
- No tracked artifact may be required to contain the SHA of the commit that contains that artifact.
  A runner records the already-existing execution checkpoint it observed before producing output;
  the later evidence/closure commit is identified by Git history or its Gate tag and does not
  rewrite the producing revision to chase its own SHA.
- Completed work-item records are immutable. A defect discovered after completion is owned by a new
  forward `C-G##-###` corrective that links to the affected record; governance must not change the
  completed work item back to `in_progress` or move lifecycle state backward. A corrective may
  block the next Gate attempt, but it does not erase or reopen history.
- `verify-fast` scans every work-item transition from the machine policy epoch as well as the
  current worktree. It rejects terminal-record deletion/reactivation even when a later commit hides
  the regression. New C/A records use their dedicated namespace; legacy I correctives retain their
  same-Gate terminal links through the machine-readable legacy registry.
- Candidate readiness is the deterministic front of Gate Eval, not a separate open-ended audit.
  Transient infrastructure failures resume the same phase/trial. An implementation, policy,
  zero-tolerance, cleanup, metric, quality, or performance failure makes that orchestration
  attempt terminally failed; correction uses the next C ID and reevaluation uses the next A ID.
- SHA and evidence-inheritance rules are provenance controls only. They must not alter Eval N,
  locked tests, Ground Truth, quality or performance thresholds, health-oracle windows, token/cost
  ceilings, or failure semantics.
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
  negative fixture, phase interface, and candidate/environment binding before it closes. The final
  Gate attempt may only orchestrate frozen runners and may not add product behavior, fixtures, or
  a test framework.
- An Iteration that adds a persistence surface, egress surface, trace stage, identity principal, or
  storage namespace proves the new surface's leakage, authorization, and observability properties
  in that same Iteration.
- An Iteration closes only with `open_evidence: []`. Evidence that cannot be completed there must be
  reclassified before closure; it is never rolled forward from a completed Iteration.
- Eval phases run in information-per-time order. Manifest debt, candidate binding, schemas, static
  inheritance, and upstream debt must pass before remote, destructive, soak, or paid work.
- Live and multi-trial matrices persist every trial atomically and resume only pending or
  infrastructure-failed trials. A transport failure never invalidates completed trials.
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
