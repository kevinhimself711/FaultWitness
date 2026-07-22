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


def test_i0012_migration_adds_durable_incident_projection() -> None:
    sql = Path("migrations/002_i0012_control_api.sql").read_text(encoding="utf-8")
    for table in (
        "incident",
        "api_idempotency",
        "event_projection",
        "feedback",
        "pending_approval",
    ):
        assert f"CREATE TABLE IF NOT EXISTS incident_owner.{table}" in sql
    assert "REFERENCES incident_owner.incident" in sql
    assert "002_i0012" in sql
    assert sql.startswith("BEGIN;") and sql.rstrip().endswith("COMMIT;")
