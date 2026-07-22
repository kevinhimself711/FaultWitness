# EVAL-G00-006 Plan

## Purpose

Audit one fixed G00 candidate revision for repository reproducibility, governance integrity, architecture and contract conformance, publication safety, dependency provenance, and all fourteen frozen design walkthroughs. This Eval does not claim that product runtime behavior exists.

## Candidate protocol

1. Create the I-0006 candidate commit and record its full SHA.
2. Run `make eval-g00` with `FW_CANDIDATE_SHA` equal to that SHA on the clean candidate checkout.
3. Require Windows and Ubuntu baseline jobs plus the Ubuntu audit job to pass for the same candidate.
4. Upload the generated CycloneDX 1.6 SBOM and audit summary as immutable CI artifacts.
5. Finalize evidence in an asset-only synchronization commit; do not change implementation or thresholds.
6. Run `make eval-g00-close`; it must reject any incomplete Iteration, non-passing Eval, open evidence, pending Iteration, or waiver.

## Blocking checks

- UTF-8, Markdown, local links, Schema, Ruff, pytest, deterministic state diagrams, and browser-rendered Mermaid.
- Four-state-machine reachability, convergence, approval, uncertainty, fencing, tenant, idempotency, and public-contract invariants.
- Full-SHA GitHub Actions, locked dependencies, compatible licenses, source ownership, secret and absolute-local-path scan.
- CycloneDX 1.6 SBOM has a fixed candidate SHA and unique versioned licensed components.
- Exactly fourteen G00 walkthroughs pass and map to the frozen I-0005 contract bindings.
- Gate closure readiness confirms all six Iterations are completed with commits and all six Evals pass with no open evidence or waivers.
- Changed assets satisfy the I-0006 record with no threshold decrease or locked-test mutation.

## Non-blocking check

External HTTP links run on a scheduled public workflow and always preserve a report. Network failure cannot waive a broken local link.

## LangSmith applicability

LangSmith is `not_applicable` for G00 because this Gate implements no Agent runtime and therefore produces no runtime trace. Later runtime Gates cannot inherit this exception.
