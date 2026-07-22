# EVAL-G00-005 Report

## Result

Result: pass.

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
| Windows baseline | pass | GitHub Actions job 88917224227 |
| Ubuntu baseline | pass | GitHub Actions job 88917224281 |

Cross-platform run: <https://github.com/kevinhimself711/FaultWitness/actions/runs/29918293502>

Evidence-finalization run: <https://github.com/kevinhimself711/FaultWitness/actions/runs/29918433105>

Protected-main confirmation: <https://github.com/kevinhimself711/FaultWitness/actions/runs/29918543956>

## Deviations

- Initial validation exposed a JSON Schema `oneOf` ambiguity because a pattern-only branch also accepted null. The store branch now declares `type: string`; no contract rule was relaxed.
- The first full local run exposed one remaining hard-coded planned-Iteration list. The regression now derives the planned set from lifecycle data, eliminating future Iteration-number coupling without weakening inference.
