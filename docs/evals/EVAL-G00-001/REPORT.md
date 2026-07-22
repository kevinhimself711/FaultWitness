# EVAL-G00-001 Report

## Result

Result: pass.

## Evidence

| Check | Environment | Status | Evidence |
| --- | --- | --- | --- |
| `make verify-fast` | Windows | pass | 27 repository files checked |
| `make eval-changed` | Windows | pass | 27 repository files checked |
| uv lock consistency | Windows | pass | `uv lock --check` |
| pnpm lock consistency | Windows | pass | Frozen lockfile install |
| Clean checkout | Windows | pass | Fresh shallow clone; both Make targets and both lock checks passed |
| Private remote metadata | GitHub | pass | Private; default branch `main`; `origin` verified |
| Required Make targets | Windows runner | pass | GitHub Actions job 88896234572 |
| Required Make targets | Ubuntu runner | pass | GitHub Actions job 88896234585 |

Cross-platform run: <https://github.com/kevinhimself711/FaultWitness/actions/runs/29911801135>

## Deviations

- The interactive workstation has Node.js 24 rather than the pinned Node.js 22.14.0. Lock consistency passed locally, and the clean Windows/Ubuntu CI jobs both ran with the pinned Node.js 22.14.0, so this is recorded as environment context rather than a waiver.
