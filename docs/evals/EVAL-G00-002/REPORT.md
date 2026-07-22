# EVAL-G00-002 Report

## Result

Result: pass.

## Evidence

| Check | Status | Evidence |
| --- | --- | --- |
| `make verify-fast` | pass | Local CLI: Ruff, 7 pytest tests, Markdown, Schema, links |
| `make eval-changed` | pass | I-0002 validated for the changed asset set |
| Six frozen negative classes | pass | 7 governance tests, including one positive repository test |
| Windows baseline | pass | GitHub Actions job 88899926967 |
| Ubuntu baseline | pass | GitHub Actions job 88899926985 |
| `main` ruleset | pass | Active Ruleset `19545995`; desired and remote rules match |

Cross-platform run: <https://github.com/kevinhimself711/FaultWitness/actions/runs/29912935245>

Ruleset evidence: <https://github.com/kevinhimself711/FaultWitness/rules>

## Deviations

- The initial private repository could not activate Rulesets on GitHub Free. The project owner explicitly approved public visibility. [AMD-0001](../../gates/G00/AMENDMENTS/AMD-0001.md) records the narrowly scoped Gate amendment and pre-publication safeguards; it is not a waiver for the full I-0006 audit.
