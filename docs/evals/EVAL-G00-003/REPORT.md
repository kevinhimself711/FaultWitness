# EVAL-G00-003 Report

## Result

Result: pass.

## Evidence

| Check | Status | Evidence |
| --- | --- | --- |
| `make verify-fast` | pass | Ruff, 14 pytest tests, Markdown, Schemas, UTF-8, links, and diff checks |
| `make eval-changed` | pass | I-0003 validated for 22 changed files |
| Evidence-policy negative cases | pass | Four dedicated evidence-policy regressions plus repository governance tests |
| Full-corpus counts | pass | 110 catalog records; 22 JDs, 84 included interviews, 2 excluded empty interviews, 1 technical reference, and 1 upstream report |
| Requirement and matrix coverage | pass | 57 requirements and 57 exact-once matrix references; 41 P0, 13 P1, and 3 integrated P2 requirements |
| Publication boundary review | pass | Candidate scan found no raw source paths, credentials, private keys, or common secret tokens |
| Windows baseline | pass | GitHub Actions job 88907609199 |
| Ubuntu baseline | pass | GitHub Actions job 88907609230 |

Cross-platform run: <https://github.com/kevinhimself711/FaultWitness/actions/runs/29915287611>

## Deviations

- The first local run correctly failed because the existing Iteration-inference regression hard-coded I-0002. The test was narrowed to prove planned bootstrap records are ignored and a new assertion verifies that the current in-progress I-0003 is selected. No validator or Gate threshold was weakened.
