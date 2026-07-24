# EVAL-G02-002 Plan — Fault Lab and Scenario DSL

## Purpose

Close I-0017 by proving the complete DSL/seed catalogue, all six adapter/oracle contracts, and a
four-family non-seed live smoke without executing the 32 Gate seeds.

## Validation set

- V-G02-004 at L1 over all 32 specifications.
- V-G02-005 at L1 over all six fault classes.
- V-G02-006 Iteration layer with four non-seed scenarios.
- Runner/fixture/interface readiness for L2 V-G02-017.

## Pass criteria

- Catalogue and adapter enumeration are exact.
- Four family smokes complete injection and exact restoration with no open evidence.
- The Gate seed IDs are not consumed by Iteration smoke.
- No 160-case payload is created.

The corrective owner pass also requires all fourteen frozen Gate phase IDs to have preimplemented
handlers, including I-0017's `lab-deploy-and-bind` and `scenario-matrix`. It unit-tests the phase
interfaces but does not execute their Gate N=1/N=32 work during the Iteration.
