# Changelog

## Unreleased

### Gate closure

- Close G00 without waivers on immutable candidate `1f36a799c27dfe0709a529448e6935d0ea3103eb`.
- Hand off to G01 in `not_started` state; no G01 implementation is authorized before its Master Plan is frozen.

### Tooling

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
