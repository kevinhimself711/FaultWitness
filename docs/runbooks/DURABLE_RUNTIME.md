# Durable runtime runbook

```powershell
uv run python -m faultwitness_dev deploy-runtime-schema
uv run python -m faultwitness_dev inspect-runtime-schema
```

Migration input bytes are digested directly and the producer commit plus dirty/clean fact is
recorded as provenance. Deployment permits targeted dirty-tree debugging and never uses provenance
as a launch gate. Inspection reads the actual schema inventory.

Migrations remain transactional and additive. Version conflicts roll back the transaction;
same-key/different-digest idempotency fails closed; Outbox/Inbox/DLQ, lease fencing, and encrypted
checkpoint semantics are unchanged. Do not drop owner data during rollback.
