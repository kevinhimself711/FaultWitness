# EVAL-G00-002 Report

## Result

Local result: pass. Cross-platform CI and ruleset evidence pending.

## Evidence

| Check | Status | Evidence |
| --- | --- | --- |
| `make verify-fast` | pass | Local CLI: Ruff, 7 pytest tests, Markdown, Schema, links |
| `make eval-changed` | pass | I-0002 validated for the changed asset set |
| Six frozen negative classes | pass | 7 governance tests, including one positive repository test |
| Windows baseline | pending | GitHub Actions |
| Ubuntu baseline | pending | GitHub Actions |
| `main` ruleset | pending | GitHub ruleset API |

## Deviations

- The desired `main` Ruleset is committed and Schema-validated, but GitHub rejected both the Rulesets and classic Branch Protection APIs for this private repository with HTTP 403: the account must upgrade to GitHub Pro or the repository must become public. Public visibility violates G00 and is not accepted as a workaround.
