# EVAL-G02-013 Report

Result: `pass`.

Candidate `09693ceb52a883113c82ac1a7be489e826bad04f` passed all four deterministic
I-0028 transport cases. A real Windows CPython child process received
`736574202d65750a7072696e7466206f6b0a`, exactly matching the caller's UTF-8 bytes and containing
no CRLF translation.

## Frozen validation ownership

- V-G02-009 Iteration N remained exactly 4 identity policies.
- V-G02-010 Iteration N remained 0.
- V-G02-011 Iteration N remained exactly 4 writer paths.
- Gate L2 execution, private-server command execution, destructive scenario, external-service call,
  and model call were all 0.

The oversized-script case kept every child-process argument below the Windows limit, transmitted
script and sudo credential through separate binary stdin sessions, and passed no timeout or text
encoding to subprocess. Execute failure still cleaned up; cleanup failure and invalid path output
remained blocking. Validation N, thresholds, Ground Truth, locked tests, health windows, model route,
token/cost ceilings, and failure semantics did not change. `open_evidence: []`.
