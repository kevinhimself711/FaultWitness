# EVAL-G01-001 Report

## Result

Result: pending.

I-0007 is active. The plaintext handoff has been parsed into six declared fields, encrypted through stdin into a repository-external SOPS + Age store, and decrypted for an in-memory round-trip check. Pinned SOPS/Age and project-specific Age/SSH identities exist outside the repository. On 2026-07-22 the operator declared all three credentials long-lived and required their values to remain unchanged; same-value acceptance is now recorded in private metadata. The handoff remains present because host pin, dedicated-key login, and the repeated capability probe are still blocking.

The strengthened publication scanner now detects both Bailian/OpenAI-shaped and LangSmith-shaped tokens and scans PowerShell/bootstrap scripts. No model or LangSmith API has been called.

## Required evidence

- Full candidate SHA and private-run identifier.
- Independent host-fingerprint confirmation, dedicated-key login, and three existing-credential acceptance records without secret material.
- Sanitized host capability report and digest.
- Secret/publication scan, host-pin negative case, and deterministic reprobe results.

## Open evidence

Open evidence: out-of-band host fingerprint confirmation, SSH key installation/login, two matching host probes, handoff deletion, immutable candidate binding, and final EVAL-G01-001 execution.

## Deviations retained

- Candidate `1bd9c712cfe565c50b8f51f015a11367ca78cc35` passed local code/document checks but was rejected before private Eval because the inherited broad `secrets/` ignore rule excluded the public `config/secrets` schema and toolchain lock. The rule is narrowed to root-only `/secrets/`; no security threshold or failed evidence was removed.
- Candidate `482e881d803fab2bdf25432d3b99170d2850038c` fixed the ignore boundary but predates the project owner's long-lived credential decision. AMD-0002 supersedes its replacement workflow without changing any stored credential value or final publication/host/capability threshold.
- The 2026-07-22 security/audit suite was intentionally run once with the retained handoff visible. Publication scanning failed closed on both API-key families in `envs.txt` without printing their values. Candidate verification therefore isolates the handoff temporarily and restores it in `finally`; final EVAL-G01-001 still requires permanent deletion and the exact `/envs.txt` ignore rule.
