---
paths: ["tests/**"]
---

## Validation ownership

Every validation belongs to exactly one layer:

- L1 runs only in its owning work package: deterministic, closed, no external dependency.
- L2 runs only on the unified Gate stack: statistical, soak, stress, destructive, live external, or
  cross-package end to end. Its owning work package must first implement and test its runner,
  negative fixture, phase interface, and real external seam where applicable.
- L3 uses the smallest sufficient work-package sample and a strictly larger Gate sample.

The same validation may not use the same N in two layers. Work that adds persistence, egress, a
trace stage, identity, or storage namespace proves the new surface's authorization, leakage, and
observability properties immediately. A work package has no deferred or open evidence at exit.
