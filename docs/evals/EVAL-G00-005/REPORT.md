# EVAL-G00-005 Report

## Result

Result: local pass; protected-main cross-platform evidence pending.

## Evidence

| Check | Status | Evidence |
| --- | --- | --- |
| `make verify-fast` | pass | Ruff, 32 pytest tests, 42 Markdown files, Schemas, UTF-8, links, and diff checks |
| `make eval-changed` | pass | I-0005 validated for the changed asset set |
| State reachability and convergence | pass | 4 machines, 52 states, and 82 transitions; zero unreachable, trapped, or terminal-outgoing states |
| R2/UNCERTAIN/lease safety | pass | 12 dedicated negative contract mutations reject approval bypass, blind retry, stale commit, and contract drift |
| OpenAPI/AsyncAPI/type/failure contracts | pass | 8 REST/SSE paths, 8 channels, 21 types, 34 Commands, 43 Events, 10 errors, and 17 fixed failures |
| Walkthrough bindings | pass | All 10 W-ARCH scenarios resolve to registered transitions, Commands, failures, and REST operations |
| Generated Mermaid | pass | Committed diagrams match the deterministic YAML renderer byte-for-byte |
| Publication boundary review | pass | Candidate scan found no local absolute path, credential, private key, or common secret token |
| Windows baseline | pending | Pull-request CI not yet recorded |
| Ubuntu baseline | pending | Pull-request CI not yet recorded |

## Deviations

- Initial validation exposed a JSON Schema `oneOf` ambiguity because a pattern-only branch also accepted null. The store branch now declares `type: string`; no contract rule was relaxed.
- The first full local run exposed one remaining hard-coded planned-Iteration list. The regression now derives the planned set from lifecycle data, eliminating future Iteration-number coupling without weakening inference.
