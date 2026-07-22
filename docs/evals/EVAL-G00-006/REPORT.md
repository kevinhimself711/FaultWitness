# EVAL-G00-006 Report

## Result

Result: local pass; fixed candidate SHA and cross-platform evidence pending.

## Candidate

- Evaluated revision: pending I-0006 candidate commit.
- Candidate kind: architecture, contract, governance, and CI baseline; no product runtime.

## Current evidence

| Check | Status | Evidence |
| --- | --- | --- |
| G00 audit unit and negative tests | pass | Secret, local path, Action pin, license, and SBOM negative cases |
| Dependency and publication audit | pass | 354 installed Python and Node components audited locally |
| Mermaid browser rendering | pass | 9 committed diagrams rendered to SVG |
| Fourteen design walkthroughs | pass | `WALKTHROUGHS.yaml` maps all frozen scenarios to contract bindings |
| `make verify-fast` | pass | Ruff, 42 pytest tests, 47 Markdown files, Schemas, UTF-8, links, and diff checks |
| `make eval-changed` | pass | I-0006 validated for the complete changed asset set |
| `make eval-g00` | pass | Full local candidate audit including 354 dependency components |
| Windows and Ubuntu candidate CI | pending | Filled after candidate commit |
| Protected-main confirmation | pending | Filled after merge |

## Applicability and limitations

- LangSmith: not applicable because G00 has no Agent runtime trace.
- Passing this Eval proves a reproducible planning, architecture, contract, evidence, and governance baseline only.
- Gate closure remains a separate asset-only commit against the immutable candidate SHA.
