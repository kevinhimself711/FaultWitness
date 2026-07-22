# EVAL-G00-002 Plan

## Purpose

Verify that repository governance is executable, cross-platform, and fail-closed for the frozen negative cases.

## Positive checks

- Parse and validate all registered governance assets.
- Run Ruff, pytest, Markdown, UTF-8, local-link, and Git-diff checks.
- Validate the changed asset set against I-0002.
- Run the same Make targets on Windows and Ubuntu.

## Negative checks

- Missing required field.
- Duplicate identifier.
- Unknown Gate or Iteration reference.
- Behavior change without documentation.
- Illegal lifecycle status.
- Gate threshold reduction.

Each negative test must assert the intended validation error; a parser crash or unrelated failure is not a pass.
