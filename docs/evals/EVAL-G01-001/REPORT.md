# EVAL-G01-001 Report

## Result

Result: **PASS**.

Final candidate `df644f10a4596232be24774bae209d1c1a4befa6` replayed the
publication scan and secure-bootstrap walkthrough without credential rotation,
secret disclosure, waiver, or open evidence.

Evaluated candidate: `7a9237c4c5b9fc0c736435e836534e72712c4169`.

Private run identifier: `EVAL-G01-001-WINDOWS-20260722-01`.

The six declared handoff fields were encrypted through stdin into a repository-external SOPS + Age store and passed an in-memory round-trip check. The operator-declared long-lived values were accepted unchanged. Out-of-band host-pin comparison, existing-password login, dedicated-key installation, and password-disabled key-only login passed. The plaintext handoff was deleted and exactly one `/envs.txt` ignore rule is present.

Two repeated allowlisted read-only probes produced the same normalized document. The candidate-bound public capability digest is `dce82edf0149a68c3c0833f8e42c02fb4443f61f945999eb56a84d5fa00dd783`. The frozen CPU, memory, kernel, cgroup, KVM, seccomp, user-namespace, Docker health, protected-port, GPU, storage, and CIDR checks all passed.

The strengthened publication scanner now detects both Bailian/OpenAI-shaped and LangSmith-shaped tokens and scans PowerShell/bootstrap scripts. No model or LangSmith API has been called.

## Blocking checks

- Encrypted round-trip and required secret-name coverage: pass.
- Existing-credential acceptance with no value change: pass.
- Independent host pin and mismatch-negative case: pass.
- Existing-password preflight and dedicated-key-only login: pass.
- Two matching candidate-bound capability probes and frozen server floor: pass.
- Pinned bootstrap tool/source integrity: pass.
- Working tree, Git tracking, report, scripts, and generated-artifact publication boundary: pass; findings 0.

## Open evidence

Open evidence: none.

Waivers: none.

No K3s installation, existing-Docker mutation, model call, or LangSmith API/trace operation was performed. Bailian and LangSmith live validity remain owned by I-0013 and I-0014.

## Deviations retained

- Candidate `1bd9c712cfe565c50b8f51f015a11367ca78cc35` passed local code/document checks but was rejected before private Eval because the inherited broad `secrets/` ignore rule excluded the public `config/secrets` schema and toolchain lock. The rule is narrowed to root-only `/secrets/`; no security threshold or failed evidence was removed.
- Candidate `482e881d803fab2bdf25432d3b99170d2850038c` fixed the ignore boundary but predates the project owner's long-lived credential decision. AMD-0002 supersedes its replacement workflow without changing any stored credential value or final publication/host/capability threshold.
- The 2026-07-22 security/audit suite was intentionally run once with the retained handoff visible. Publication scanning failed closed on both API-key families in `envs.txt` without printing their values. Candidate verification therefore isolates the handoff temporarily and restores it in `finally`; final EVAL-G01-001 still requires permanent deletion and the exact `/envs.txt` ignore rule.
- The first dedicated-key installation attempt failed because Windows OpenSSH did not invoke a `.cmd` askpass helper; a no-secret sentinel proved the password was never supplied. The batch helper was removed and replaced with a repository-source-digest-locked C# executable built outside Git. Dummy-value self-test, existing-password preflight, key installation, and password-disabled key login then passed.
- The first host probe on candidate `f5d7e103681d4c6a95bbb5d80462e496261f7786` failed on a valid Docker `IPAM.Config = null` response. Shape handling now treats null as no configured subnet and malformed shapes as conflict. A subsequent diagnostic baseline was rejected rather than published because it bound the superseded candidate and measured the current Python process's seccomp mode instead of kernel seccomp capability. Both defects have regression tests; the frozen seccomp threshold remains `true`.
- EVAL-G01-001 passed while I-0007 was the sole active Iteration, as required. A post-pass rerun after staging the lifecycle transition to `completed` was rejected by that same precondition; closure assets were instead checked by `verify-fast` and `eval-changed`, with no implementation or threshold change.
