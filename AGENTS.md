---
active_gate: G02
active_gate_status: not_started
active_iteration: null
last_closed_gate: G01
---

# FaultWitness Repository Instructions

## Mission and current phase

FaultWitness is a multi-tenant Agent Runtime for investigating microservice incidents, proposing bounded remediations, executing approved actions, and producing auditable evaluation and training assets.

G00 and G01 are closed. G02 is `not_started`, no Iteration is active, and the
G02 placeholder is not a decision-complete Master Plan. No G02 implementation,
live evaluation, deployment mutation, or scope claim is authorized until a
dedicated planning turn freezes the G02 Master Plan in a planning commit.

## Source-of-truth order

When artifacts disagree, use this precedence and stop to resolve the drift instead of silently choosing one:

1. The authoritative final project plan.
2. The active Gate plan and accepted ADRs.
3. Versioned public contracts and machine-readable state-machine specifications.
4. Tests and implementation.
5. Generated reports and explanatory documentation.

PROJECT_STATE.yaml is the authority for the active Gate and iteration, not for architecture semantics.

## Required workflow

- No behavioral change may begin without an iteration plan.
- A Gate Master Plan must be frozen before its implementation iterations start.
- Behavioral changes, affected tests, documentation, and version manifests belong in the same commit.
- Do not lower a Gate threshold, modify locked tests, or alter ground truth in an implementation commit.
- Failed Gates, negative experiments, and rejected architectures must remain in the repository history.
- Gate closure is a separate asset-only commit evaluated against an immutable candidate SHA.
- A final Gate-audit Iteration may only orchestrate frozen checks, reverify one candidate,
  and synchronize evidence. It may not add product behavior or a substantial Eval framework;
  missing harness work returns to an owning Iteration and creates a new candidate.
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
- Gate closure must update the controlled root/status asset set, including `AGENTS.md`,
  `PROJECT_STATE.yaml`, `README.md`, and `docs/roadmap/PHASES.md`, and their lifecycle fields
  must agree before verification passes.
- Live external-service matrices must persist each trial atomically and resume only failed or
  pending trials. A single attributable transport failure must not discard completed trials.
- Once a failure has a verified root cause, no generic operator-adjudicated pass path may remain;
  the root cause is fixed and the affected phase is rerun under its normal blocking semantics.
- Do not commit or push unless the user explicitly requests it.

Planning-only commits may create or refine future Iteration and Eval assets without activating them. They never authorize product behavior, infrastructure mutation, credential use, or live evaluation.

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
