# EVAL-G00-004 Report

## Result

Result: pass.

## Evidence

| Check | Status | Evidence |
| --- | --- | --- |
| `make verify-fast` | pass | Ruff, 19 pytest tests, 37 Markdown files, Schemas, UTF-8, links, and diff checks |
| `make eval-changed` | pass | I-0004 validated for the changed asset set |
| Architecture model | pass | 15 components, 9 stores, 6 unique state owners, 9 trust boundaries, and 4 mandatory prohibited paths |
| Architecture negative cases | pass | Five dedicated plane, owner, walkthrough, bypass, and ADR regressions |
| Architecture walkthroughs | pass | W-ARCH-001 through W-ARCH-010 resolve to known components and fixed outcomes |
| Architecture documents | pass | Five Mermaid views exist and mutually cross-link; initial Threat Model and six accepted ADRs resolve |
| Publication boundary review | pass | Candidate scan found no local absolute path, credential, private key, or common secret token |
| Windows baseline | pass | GitHub Actions job 88911330239 |
| Ubuntu baseline | pass | GitHub Actions job 88911330145 |

Cross-platform run: <https://github.com/kevinhimself711/FaultWitness/actions/runs/29916449844>

## Deviations

- The first local run exposed lifecycle-coupled tests that hard-coded the current Iteration number. They were replaced with stable properties for planned-only and highest-eligible inference. No governance behavior or Gate threshold was weakened.
