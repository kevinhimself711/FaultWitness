# EVAL-G01-001 Plan — Secure Bootstrap and Capability Baseline

## Purpose

Prove that the operator-declared long-lived project credentials and host identity can be bootstrapped without entering Git or public evidence, and freeze a sanitized pre-mutation server baseline. This Eval changes no credential value and authorizes no deployment or live model/trace request.

## Candidate protocol

1. Select I-0007, move it to `in_progress`, and create a candidate commit before using any secret.
2. Verify the manually supplied host fingerprint, dedicated SSH key, external Age identity, and SOPS policy.
3. Migrate each existing credential directly to the protected store, record explicit operator acceptance without changing values, verify server login, then delete and precisely ignore `envs.txt`.
4. Collect server/Docker/network/kernel/KVM/GPU/storage facts through allowlisted probes and emit only sanitized fields.
5. Bind commands, sanitized artifact digests, secret versions, and candidate SHA in the report; never record values, suffixes, reversible hashes, IP, user, or private path.

## Blocking checks

- Secret canaries across working tree, Git history, stdout/stderr, report, process arguments, temporary files, and generated artifacts.
- Host-key mismatch, missing key, wrong identity, missing SOPS policy, and attempted plaintext output all fail closed.
- Existing values remain unchanged; server login succeeds before finalization, while Bailian and LangSmith live verification remains owned by I-0013 and I-0014.
- Capability report covers existing Docker health/listeners/networks, K3s prerequisites, cgroup/kernel, KVM, RuntimeClass prerequisites, GPU, disk, memory, and port/CIDR conflicts.

## Pass criteria

- Public secret, host locator, login identity, and reversible credential fingerprint findings: 0.
- `envs.txt` is absent and ignored after verified migration, explicit acceptance, host pin, server login, and dedicated-key login; two matching capability probes remain mandatory for Eval pass but do not prolong plaintext retention.
- Dedicated SSH and pinned host identity pass; mismatch is rejected.
- Two repeated probes produce the same normalized capability document and candidate binding.

## Evidence contract

Raw probe output and credential operations remain private. Git stores only the sanitized report, digests, versions/timestamps, command names, and evidence references. LangSmith is a required G01 dependency but is not called by this bootstrap Eval.
