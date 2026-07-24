# EVAL-G02-014 Report

Result: `fail`.

Candidate `cfafa5a6f1510a1a7c8fe2c9360284214c8734f2` passed the four frozen
fail-fast preflights and `lab-deploy-and-bind`. The preflights proved all 13 required manifests,
the exact candidate/evidence binding, 23 frozen subject digests including the corrected transport,
and all nine G01 manifests. The lab bound the expected image-set digest and reported all 24
Deployments ready.

## Blocking result

`isolation-access-matrix` stopped during candidate-bound provisioning before its first access cell.
The runner initially recorded `infra_failed: remote_probe_transport`; two bounded diagnostic
attempts exposed the hidden deterministic cause: the frozen private host provides Python 3.8, while
`deploy/g02/gate_probe.py` imports `UTC` from `datetime`, which exists only in Python 3.11 and later.
The remote interpreter raised:

```text
ImportError: cannot import name 'UTC' from 'datetime' (/usr/lib/python3.8/datetime.py)
```

This is a deterministic runner compatibility defect, not transient infrastructure. The phase is
therefore finally adjudicated `blocked`; the same candidate is not resumed. Provisioning did not
complete, all 60 access cells remained unexecuted, and later phases correctly did not start.

## Adjudication

I-0029 is terminally failed with complete negative evidence and `open_evidence: []`. A forward
corrective Iteration must replace the Python-version-specific UTC dependency and prove the probe
under Python 3.8 locally; a later replacement orchestration must use a new candidate and Eval ID.

Trace stages, canary surfaces, destructive scenarios, deterministic baselines, external-service
probes, and model calls all remained zero. No validation N, threshold, Ground Truth, locked test,
health window, model route, token/cost ceiling, destructive-once rule, or failure semantic changes.
