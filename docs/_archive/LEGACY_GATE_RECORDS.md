# Legacy gate records under `governance/gates/`

`governance/gates/G00.yaml`, `G01.yaml`, and `G02.yaml` are legacy evidence for closed gates.
They are immutable historical record in the same category as the `governance/iterations/*.yaml`
files and `governance/policies/iteration-lifecycle-v1.yaml`: retained, never edited, never
extended.

`governance/ASSETS.yaml` at `schema_version: "2.0.0"` no longer lists `governance/gates/*.yaml`,
and `schemas/governance/gate.schema.json` is no longer referenced by any asset entry. Nothing
validates these files, and `validate_repository_schemas` does not read them.

**There is deliberately no `governance/gates/G03.yaml`.** Its deletion is part of the Governance
v2 migration, not an oversight, and it must not be recreated — `AGENTS.md` forbids re-creating
per-Iteration lifecycle YAML, Gate-attempt records, and closure state mirrors, and a machine-
readable G03 gate record would be exactly such a mirror. G03's authority lives in two places
instead:

- `docs/gates/G03/PLAN.md` holds the frozen exits, which planning may make decision-complete but
  may not lower: validation E2E at least 5 percentage points above the best G02 baseline, 100% of
  critical conclusions traceable to an EvidenceRef, and Worker/SSE recovery without lost or
  duplicated state.
- `PROJECT_STATE.yaml` holds the machine-readable gate state (`active_gate`,
  `active_gate_status`, `last_closed_gate`, `active_plan`, `active_report`, `latest_release`),
  validated against `schemas/governance/project-state.schema.json`, which is
  `additionalProperties: false`.

A reader looking for "the G03 gate file" should read `docs/gates/G03/PLAN.md` and
`PROJECT_STATE.yaml`. The absence of a YAML gate record is the intended end state.
