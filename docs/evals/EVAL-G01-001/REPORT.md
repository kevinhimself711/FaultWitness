# EVAL-G01-001 Report

## Result

Result: pending.

I-0007 is active. The plaintext handoff has been parsed into six declared fields, encrypted through stdin into a repository-external SOPS + Age store, and decrypted for an in-memory round-trip check. Pinned SOPS/Age and project-specific Age/SSH identities exist outside the repository. The handoff remains present because host pin, dedicated-key login, three rotations, and the repeated capability probe are still blocking.

The strengthened publication scanner now detects both Bailian/OpenAI-shaped and LangSmith-shaped tokens and scans PowerShell/bootstrap scripts. No model or LangSmith API has been called.

## Required evidence

- Full candidate SHA and private-run identifier.
- Independent host-fingerprint confirmation, dedicated-key login, and three replacement-credential rotations without secret material.
- Sanitized host capability report and digest.
- Secret/publication scan, host-pin negative case, and deterministic reprobe results.

## Open evidence

Open evidence: out-of-band host fingerprint confirmation, SSH key installation/login, server/Bailian/LangSmith rotation, two matching host probes, handoff deletion, immutable candidate binding, and final EVAL-G01-001 execution.

## Deviations retained

- Candidate `1bd9c712cfe565c50b8f51f015a11367ca78cc35` passed local code/document checks but was rejected before private Eval because the inherited broad `secrets/` ignore rule excluded the public `config/secrets` schema and toolchain lock. The rule is narrowed to root-only `/secrets/`; no security threshold or failed evidence was removed.
