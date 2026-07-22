# EVAL-G01-001 Report

## Result

Result: pending.

I-0007 is active. The six declared handoff fields were encrypted through stdin into a repository-external SOPS + Age store and passed an in-memory round-trip check. The operator declared all three credentials long-lived and required their values to remain unchanged; same-value acceptance is recorded in private metadata. Out-of-band host-pin comparison, existing-password login, dedicated-key installation, and key-only login passed. The plaintext handoff was then deleted and the exact `/envs.txt` rule added. Two matching capability probes and candidate-bound EVAL-G01-001 remain pending.

The strengthened publication scanner now detects both Bailian/OpenAI-shaped and LangSmith-shaped tokens and scans PowerShell/bootstrap scripts. No model or LangSmith API has been called.

## Required evidence

- Full candidate SHA and private-run identifier.
- Independent host-fingerprint confirmation, dedicated-key login, and three existing-credential acceptance records without secret material: captured in private evidence and passing.
- Sanitized host capability report and digest.
- Secret/publication scan, host-pin negative case, and deterministic reprobe results.

## Open evidence

Open evidence: two matching host probes, immutable candidate binding, and final EVAL-G01-001 execution.

## Deviations retained

- Candidate `1bd9c712cfe565c50b8f51f015a11367ca78cc35` passed local code/document checks but was rejected before private Eval because the inherited broad `secrets/` ignore rule excluded the public `config/secrets` schema and toolchain lock. The rule is narrowed to root-only `/secrets/`; no security threshold or failed evidence was removed.
- Candidate `482e881d803fab2bdf25432d3b99170d2850038c` fixed the ignore boundary but predates the project owner's long-lived credential decision. AMD-0002 supersedes its replacement workflow without changing any stored credential value or final publication/host/capability threshold.
- The 2026-07-22 security/audit suite was intentionally run once with the retained handoff visible. Publication scanning failed closed on both API-key families in `envs.txt` without printing their values. Candidate verification therefore isolates the handoff temporarily and restores it in `finally`; final EVAL-G01-001 still requires permanent deletion and the exact `/envs.txt` ignore rule.
- The first dedicated-key installation attempt failed because Windows OpenSSH did not invoke a `.cmd` askpass helper; a no-secret sentinel proved the password was never supplied. The batch helper was removed and replaced with a repository-source-digest-locked C# executable built outside Git. Dummy-value self-test, existing-password preflight, key installation, and password-disabled key login then passed.
