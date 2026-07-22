from pathlib import Path


def test_i0011_migration_contains_atomic_runtime_primitives() -> None:
    sql = Path("migrations/001_i0011_durable_runtime.sql").read_text(encoding="utf-8")

    for schema in ("incident_owner", "task_owner", "graph_owner", "action_owner"):
        assert f"CREATE SCHEMA IF NOT EXISTS {schema}" in sql
    for primitive in (
        "aggregate_state",
        "idempotency",
        "outbox",
        "inbox",
        "dead_letter",
        "checkpoint",
        "lease",
    ):
        assert primitive in sql
    assert "REVOKE ALL ON SCHEMA" in sql
    assert sql.startswith("BEGIN;")
    assert sql.rstrip().endswith("COMMIT;")
