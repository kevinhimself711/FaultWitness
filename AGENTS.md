# FaultWitness Repository Instructions

## Mission and current state

FaultWitness is a multi-tenant Agent Runtime for incident investigation, bounded remediation,
auditable evaluation, and training-data production. G00, G01, and G02 are closed without waiver.
G03 is `not_started`; its placeholder authorizes planning only.

`PROJECT_STATE.yaml` is the only current lifecycle state. Root documents and roadmap pages describe
state but do not mirror machine lifecycle fields.

## Governance v2

- Freeze one decision-complete Gate Plan before implementation. The plan owns scope, non-goals,
  metric definitions, validation layers, budgets, external seams, and failure semantics.
- Freeze definitions, not unknowns. Procedure, safety boundaries, metric definitions, failure
  semantics, and `diagnostic_only` handling freeze before implementation. A numeric target that
  references a measured quantity does not: the plan freezes the target's *form* and margin, for
  example `best_baseline + 0.05`, and records the reference value as pending until one run passes
  the instrument-validity checks under Experiments and evidence. Never anchor a target to a number
  the instrument has not yet been shown to measure correctly.
- A frozen target that becomes mathematically unreachable is a design defect, not a metric to
  satisfy. Stop and report the infeasibility together with the measurement that produced it, then
  propose a task-shape or scope change. Do not cap the target, exclude the winning comparison arm,
  lower a floor, or adjust a predicate so a label reads better.
- Do not create per-Iteration lifecycle YAML, Eval placeholders, activation records, corrective
  records, Gate-attempt records, evidence-head commits, or closure state mirrors.
- A planned work package may be a section or table row in the Gate Plan. Small defects discovered
  during execution stay in the same work package and use the direct debug loop below.
- Historical G00–G02 Gate, Iteration, Eval, policy, schema, and I/C/A assets are immutable legacy
  evidence. They are not active templates or CI inputs. Reproduce them by checking out the
  corresponding `gate/G##-v#` tag.
- Documentation, reports, and governance edits never invalidate runtime or Eval evidence.
- Two consecutive governance-only actions without a new runtime observation are an orchestration
  deadlock. Delete or bypass the non-semantic blocker and resume the experiment.
- The user's latest explicit instruction for the active task supersedes stale Goal or workflow
  wording. This never authorizes weaker safety, security, Eval N, thresholds, or failure semantics.
  Re-deriving a threshold's reference value from the first valid measurement is not weakening when
  the previously anchored value is shown to come from an instrument defect; name the defect, and
  leave the target's form and margin unchanged.
- Do not commit or push unless the user explicitly requests it.

## Direct debug loop

Use this loop for a deterministic defect in an existing implementation or runner:

1. Read the failed trial or phase artifact and identify one falsifiable root cause.
2. Apply the smallest fix to the existing semantic branch and existing runner.
3. Run the targeted unit test and, for an external boundary, one real-seam proof.
4. Replay only failed trials and dependencies whose named runtime checkpoints changed.
5. Resume the same experiment journal. Summarize root causes and fixes once in the Gate Report.

Do not add a bespoke harness, lifecycle, manifest, or status commit around this loop. New product
scope, a new metric, a threshold change, or a substantial new framework requires a Gate Plan
amendment before implementation.

## Validation ownership

Every validation belongs to exactly one layer:

- L1 runs only in its owning work package: deterministic, closed, no external dependency.
- L2 runs only on the unified Gate stack: statistical, soak, stress, destructive, live external, or
  cross-package end to end. Its owning work package must first implement and test its runner,
  negative fixture, phase interface, and real external seam where applicable.
- L3 uses the smallest sufficient work-package sample and a strictly larger Gate sample.

The same validation may not use the same N in two layers. Work that adds persistence, egress, a
trace stage, identity, or storage namespace proves the new surface's authorization, leakage, and
observability properties immediately. A work package has no deferred or open evidence at exit.

## Experiments and evidence

- Persist every live or multi-trial result atomically. `execution_attempt` increments only when work
  executes again; `record_version` increments when the journal document changes.
- When a semantic fix starts a new execution, preserve the prior terminal record and its last
  side-effect/observation checkpoints in the same trial journal history.
- Resume pending or infrastructure-failed trials. Do not discard passed independent trials after a
  transport failure or an unrelated fix.
- Cache and invalidation use named semantic checkpoints such as `sut`, `identity_and_storage`,
  `trace_service`, and `model_route`. A global Git SHA or aggregate evaluator digest is provenance,
  not a reason to invalidate every phase.
- Record the actual producer commit, image/config/dataset/model/locked-test/Ground-Truth digests,
  environment facts, timestamps, inputs, outputs, and artifact digests with the experiment.
- When Gate closure commits are explicitly authorized, create one release commit containing the
  implementation, tests, and Gate Report; point the Gate tag to it; then use at most one state/
  manifest documentation commit to record the known release SHA and artifact digests. The later
  documentation commit has no evidence identity and cannot invalidate experiments. There is no
  candidate/evidence/governance multi-SHA state machine, HEAD equality requirement, changed-path
  allowlist, or self-referential `evaluated_revision` chase.
- Prove the instrument before spending model budget, cheapest check first: (1) leakage probe, can a
  zero-model classifier over the same inputs reach the target score; (2) divergence, do the
  comparison arms separate at all and is the interval width non-zero; (3) disclosure symmetry, is
  every scoring rule stated to every measured arm, and does no comparison arm receive by
  construction what the others must infer. Only then buy trials.
- Disclosure symmetry is a blocking check because its failure mode is a *passing* gate. A rubric the
  measured arms were never told, which a comparison arm satisfies by construction, manufactures the
  separation the statistical criterion exists to detect.
- Pre-register the expected numbers and the expected verdict before a scored run, then record the
  measured outcome even when it falsifies them. A recomputation is not a measurement; state that in
  the pre-registration so the result cannot be reinterpreted afterwards.
- Destructive and soak work executes once for unchanged semantic checkpoints. Freeze pass,
  metric-fail, infrastructure-fail, attribution, and cleanup semantics in the Gate Plan.
- Do not kill normally progressing work with a preset wall-clock timeout. Stop only at a terminal
  result, deterministic failure, verified loss of progress, or owner cancellation. This rule never
  changes Eval N, thresholds, health windows, token/cost ceilings, or failure semantics.
- A zero-tolerance criterion must name a runner, a negative fixture, and a reviewable artifact.
- Once a root cause is known, no operator-adjudicated pass path remains; fix and replay normally.

## External seams

- Before a Gate-scale live run, execute every new client/platform/credential/image/interpreter/
  protocol operation once in the target environment. Mocks and schema checks prove shape only.
- Use explicit bytes and decoding for subprocess, SSH, credential, script, and structured stdin
  transport. Cross-platform claims require a real child-process byte comparison.
- Journal side-effect checkpoints before later relay, collection, or aggregation can fail.
  Deterministic identities must bind deterministic payloads or persist a nonce before side effects.
- Repeated environment attempts have no numeric or time ceiling, but a known deterministic cause
  must be fixed before retry. Unchanged retry is reserved for classified transient infrastructure.

## Architecture and safety invariants

- Incident, Runtime Task, Agent Graph, and ActionTransaction remain separate state machines.
- Tenant identity comes only from authenticated context; request bodies cannot override it.
- The Agent cannot execute arbitrary shell commands or write directly to Kubernetes.
- Action Executor is the sole write boundary and enforces policy, approval, idempotency,
  postconditions, and compensation. R2 requires a valid immutable approval digest.
- At-least-once delivery pairs with idempotent actions; UNCERTAIN outcomes never blind-retry.
- Ground Truth and locked tests are inaccessible to Agent runtime.
- Never store private chain of thought, credentials, decrypted secrets, or restricted source bodies.
- Public CI receives no privileged cluster, provider, or production-like secret.
- Privileged infrastructure, chaos, and live-model work requires explicit user authorization. Once
  granted for the active task, do not ask repeatedly for the same authority.

Changes to these invariants require an ADR, migration/replay analysis, and targeted tests.

## Active verification

The canonical local command is:

    uv run python -m faultwitness_dev verify-fast

It checks active schemas and contracts, lint, tests, Markdown, UTF-8, links, clean diffs, and the
local repository publication audit (lockfiles, pinned Actions, licenses, ownership, secret/path
leaks, and SBOM). It does not scan historical lifecycle transitions, infer changed-path
authorization, bind evidence to HEAD, or rerun Gate Evals. Ubuntu and Windows CI are advisory
cross-platform signals; they are not remote branch-merge prerequisites.
