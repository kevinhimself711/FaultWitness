# EVAL-G02-012 Report

Result: `fail`.

Candidate `a5c282cbd587202cb24cd6b1fcc1e57d9785acd6` failed during the sanitized
environment probe required to prepare its candidate binding. No candidate-binding journal was
created and none of the fourteen frozen Gate phases entered its runner.

## Blocking result

The post-I-0026 privileged transport uploaded a shell script with
`subprocess.run(..., text=True, input=script)`. On the Windows orchestrator, Python translated each
LF byte to CRLF before SSH received stdin. `/bin/sh` therefore received a CRLF script and returned
exit 2 as `remote_command_or_transport_failed`.

A local real-child-process byte probe reproduced the exact conversion:

- text mode: `736574202d65750d0a7072696e7466206f6b0d0a`
- binary mode: `736574202d65750a7072696e7466206f6b0a`

This is a deterministic I-0026 implementation defect missed by mock runners, not a transient
remote infrastructure failure. The unchanged candidate was not retried.

## Adjudication

I-0027 is terminally failed with complete negative evidence and `open_evidence: []`. No access
cell, trace stage, canary surface, destructive scenario, deterministic baseline, external-service
probe, or model call ran. A forward corrective Iteration must make stdin byte-exact and prove real
Windows subprocess behavior; a later replacement orchestration must use a new Eval identity.

No validation N, threshold, Ground Truth, locked test, health window, model route, token/cost
ceiling, destructive-once rule, or failure semantic changes.
