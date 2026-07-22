# EVAL-G01-001 Plan — Secure Bootstrap and Capability Baseline

## Purpose

Prove that project credentials and host identity can be bootstrapped without entering Git or public evidence, and freeze a sanitized pre-mutation server baseline. This Eval authorizes no deployment or live model/trace request beyond replacement-credential verification explicitly approved by I-0007.

## Candidate protocol

1. Select I-0007, move it to `in_progress`, and create a candidate commit before using any secret.
2. Verify the manually supplied host fingerprint, dedicated SSH key, external Age identity, and SOPS policy.
3. Migrate each credential directly to the protected store, verify the replacement, revoke or rotate the handoff credential, then delete and precisely ignore `envs.txt`.
4. Collect server/Docker/network/kernel/KVM/GPU/storage facts through allowlisted probes and emit only sanitized fields.
5. Bind commands, sanitized artifact digests, secret versions, and candidate SHA in the report; never record values, suffixes, reversible hashes, IP, user, or private path.

## Blocking checks

- Secret canaries across working tree, Git history, stdout/stderr, report, process arguments, temporary files, and generated artifacts.
- Host-key mismatch, missing key, wrong identity, missing SOPS policy, and attempted plaintext output all fail closed.
- Replacement credential succeeds before old credential revocation; rollback never restores a plaintext repository file.
- Capability report covers existing Docker health/listeners/networks, K3s prerequisites, cgroup/kernel, KVM, RuntimeClass prerequisites, GPU, disk, memory, and port/CIDR conflicts.

## Pass criteria

- Public secret, host locator, login identity, and reversible credential fingerprint findings: 0.
- `envs.txt` is absent and ignored only after verified migration and rotation.
- Dedicated SSH and pinned host identity pass; mismatch is rejected.
- Two repeated probes produce the same normalized capability document and candidate binding.

## Evidence contract

Raw probe output and credential operations remain private. Git stores only the sanitized report, digests, versions/timestamps, command names, and evidence references. LangSmith is a required G01 dependency but is not called by this bootstrap Eval.
