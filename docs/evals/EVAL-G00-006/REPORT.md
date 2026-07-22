# EVAL-G00-006 Report

## Result

Result: reopened; the prior candidate passed, but final handoff-correction evidence is pending.

## Candidate

- Prior evaluated revision: `42b97088743d7741c7be4c7e0364794e31bbc59c`.
- Current evaluated revision: pending handoff-correction candidate.
- Protected-main revision: `ff87f7a16bd674143462c2d19726c7528b1ee588`.
- Candidate kind: architecture, contract, governance, and CI baseline; no product runtime.

## Current evidence

| Check | Status | Evidence |
| --- | --- | --- |
| G00 audit unit and negative tests | pass | Secret, local path, Action pin, license, and SBOM negative cases |
| Dependency and publication audit | pass | 354 local Windows components and 353 locked Ubuntu components audited; platform-only dependency difference |
| Mermaid browser rendering | pass | 9 committed diagrams rendered to SVG |
| Fourteen design walkthroughs | pass | `WALKTHROUGHS.yaml` maps all frozen scenarios to contract bindings |
| `make verify-fast` | pass | Ruff, 42 pytest tests, 47 Markdown files, Schemas, UTF-8, links, and diff checks |
| `make eval-changed` | pass | I-0006 validated for the complete changed asset set |
| `make eval-g00` | pass | Full local candidate audit including 354 dependency components |
| Windows and Ubuntu candidate CI | pass | GitHub Actions run 29931164225; all three jobs passed |
| Immutable audit artifact | pass | Artifact 8534115105 is named for and internally records the exact candidate SHA |
| Protected-main confirmation | pass | GitHub Actions run 29931318776; all three jobs passed after merge |
| Active main Ruleset | pass | Ruleset 19545995 requires both platform checks and the Ubuntu audit |

Candidate run: <https://github.com/kevinhimself711/FaultWitness/actions/runs/29931164225>

Audit artifact: <https://github.com/kevinhimself711/FaultWitness/actions/runs/29931164225/artifacts/8534115105>

Protected-main run: <https://github.com/kevinhimself711/FaultWitness/actions/runs/29931318776>

## Applicability and limitations

- LangSmith: not applicable because G00 has no Agent runtime trace.
- Passing this Eval proves a reproducible planning, architecture, contract, evidence, and governance baseline only.
- Gate closure remains a separate asset-only commit against the immutable candidate SHA.

## Deviations retained

- Candidate `91e9187d01a28c55063c149bcb4144165c71b9bf` passed the audit itself, but run 29930777384 failed because the artifact action excluded the hidden `.audit` directory. The workflow now explicitly includes hidden files; no audit threshold changed.
- Candidate `57719e84e75de332f287efb1c080079319ef5df3` passed all checks in run 29930973690, but its artifact display name used the PR merge-ref SHA. It was superseded so both the artifact name and content bind to the evaluated head SHA.
- The full Gate readiness audit against `530a285f1e461b6bf72da8eb36101e6888ca16ae` passed executable checks but found that `PROJECT_STATE` could not encode the frozen `not_started` G01 handoff. I-0006 was reopened to add the missing lifecycle value and a regression test; no Gate threshold was lowered.
