# EVAL-G00-006 Report

## Result

Result: reopened; prior candidates passed, but closure-protocol evidence is pending.

## Candidate

- Prior evaluated revision: `42b97088743d7741c7be4c7e0364794e31bbc59c`.
- Evaluated revision: `b1bc31681056bbcf6998ba6ea0a509bc9ae1ade9`.
- Evaluated revision: `b6d5f4d7a3956586bd0bb3bd8cc0eb404e7150e9`.
- Current evaluated revision: pending closure-protocol candidate.
- Protected-main revision: `ba4960ef1ce4dde1a475c4b37727365b119e56c3`.
- Protected-main revision: `dbc825dca17b9bf81013e1b2607ffc5bca5a6293`.
- Candidate kind: architecture, contract, governance, and CI baseline; no product runtime.

## Current evidence

| Check | Status | Evidence |
| --- | --- | --- |
| G00 audit unit and negative tests | pass | Secret, local path, Action pin, license, and SBOM negative cases |
| Dependency and publication audit | pass | 354 local Windows components and 353 locked Ubuntu components audited; platform-only dependency difference |
| Mermaid browser rendering | pass | 9 committed diagrams rendered to SVG |
| Fourteen design walkthroughs | pass | `WALKTHROUGHS.yaml` maps all frozen scenarios to contract bindings |
| `make verify-fast` | pass | Ruff, 48 pytest tests, 47 Markdown files, Schemas, UTF-8, links, and diff checks |
| `make eval-changed` | pass | I-0006 validated for the complete changed asset set |
| `make eval-g00` | pass | Full local candidate audit including 354 dependency components |
| Windows and Ubuntu candidate CI | pass | GitHub Actions run 29932872592; all three jobs passed |
| Immutable audit artifact | pass | Artifact 8534820581 is named for and internally records the exact candidate SHA |
| Protected-main confirmation | pass | GitHub Actions run 29932988123; all three jobs passed after merge |
| Pre-sync closure rejection | pass | `eval-g00-close` rejected active I-0006 evidence with exit 1 |
| Closure readiness cases | pass | Complete evidence accepted; incomplete Iteration failed Eval open evidence and waiver rejected |
| Active main Ruleset | pass | Ruleset 19545995 requires both platform checks and the Ubuntu audit |

Candidate run: <https://github.com/kevinhimself711/FaultWitness/actions/runs/29932872592>

Audit artifact: <https://github.com/kevinhimself711/FaultWitness/actions/runs/29932872592/artifacts/8534820581>

Protected-main run: <https://github.com/kevinhimself711/FaultWitness/actions/runs/29932988123>

## Applicability and limitations

- LangSmith: not applicable because G00 has no Agent runtime trace.
- Passing this Eval proves a reproducible planning, architecture, contract, evidence, and governance baseline only.
- Gate closure remains a separate asset-only commit against the immutable candidate SHA.

## Deviations retained

- Candidate `91e9187d01a28c55063c149bcb4144165c71b9bf` passed the audit itself, but run 29930777384 failed because the artifact action excluded the hidden `.audit` directory. The workflow now explicitly includes hidden files; no audit threshold changed.
- Candidate `57719e84e75de332f287efb1c080079319ef5df3` passed all checks in run 29930973690, but its artifact display name used the PR merge-ref SHA. It was superseded so both the artifact name and content bind to the evaluated head SHA.
- The full Gate readiness audit against `530a285f1e461b6bf72da8eb36101e6888ca16ae` passed executable checks but found that `PROJECT_STATE` could not encode the frozen `not_started` G01 handoff. I-0006 was reopened to add the missing lifecycle value and a regression test; no Gate threshold was lowered.
- The final coverage audit found that `eval-g00` did not machine-reject incomplete Iteration/Eval closure evidence. I-0006 was reopened to add `eval-g00-close` and negative cases for incomplete work, failed or open Eval evidence, and waivers.
- A closure dry run found that `eval-changed` had no explicit path for the frozen asset-only close commit. I-0006 was reopened to admit exactly nine named closure assets under the exact G00-to-G01 state transition and reject every additional path.
