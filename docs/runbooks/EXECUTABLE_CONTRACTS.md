# Executable contracts runbook

```text
uv run python -m faultwitness_dev compile-contracts
uv run python -m faultwitness_dev check-contracts
uv run python -m faultwitness_dev verify-fast
```

Generated contracts, strict boundary models, owner-separated state machines, registered predicates,
version/fencing/idempotency guards, and private-reasoning rejection remain active. Contract changes
ship with their generated resource and targeted tests. Verification is limited to current contracts
and does not traverse historical lifecycle records.
