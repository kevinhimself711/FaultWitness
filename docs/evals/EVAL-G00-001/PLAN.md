# EVAL-G00-001 Plan

## Purpose

Verify the I-0001 repository, toolchain, and private-remote baseline without evaluating product behavior.

## Evaluated surfaces

- Required root assets and version pins.
- uv and pnpm lockfile consistency.
- UTF-8 text, Markdown local links, and Git whitespace.
- Repository boundary: raw parent research materials are not tracked.
- Required Make targets on Windows and Ubuntu.
- GitHub visibility, origin URL, and default branch.

## Commands

```text
make verify-fast
make eval-changed
uv lock --check
pnpm install --lockfile-only --frozen-lockfile
git diff --check
```

The cross-platform run uses a temporary validation branch with SHA-pinned Actions. The branch is deleted after the immutable run URL and job results are captured.
