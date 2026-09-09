# ruff: noqa: E501 -- remote shell commands stay literal for auditability.

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.infra import run_remote_script
from faultwitness_dev.provenance import producer_provenance


def deploy_runtime_schema(root: Path) -> dict[str, Any]:
    migrations = sorted((root / "migrations").glob("*.sql"))
    if not migrations:
        raise GovernanceError("runtime migrations are absent")
    provenance = producer_provenance(root, migrations)
    payload = b"\n".join(migration.read_bytes() for migration in migrations)
    encoded = base64.b64encode(payload).decode()
    digest = hashlib.sha256(payload).hexdigest()
    script = f"""set -eu
work=$(mktemp -d /tmp/faultwitness-runtime.XXXXXX)
trap 'rm -rf "$work"' EXIT HUP INT TERM
printf %s {encoded} | base64 -d >"$work/migration.sql"
test "$(sha256sum "$work/migration.sql" | awk '{{print $1}}')" = {digest}
/usr/local/bin/k3s kubectl -n fw-data cp "$work/migration.sql" postgres-0:/tmp/fw-migration.sql
/usr/local/bin/k3s kubectl -n fw-data exec postgres-0 -- sh -ec \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/fw-migration.sql >/dev/null'
/usr/local/bin/k3s kubectl -n fw-data exec postgres-0 -- rm -f /tmp/fw-migration.sql
"""
    run_remote_script(script, privileged=True)
    return {
        "producer_sha": provenance.producer_sha,
        "source_digest": provenance.source_digest,
        "dirty": provenance.dirty,
        "migration_sha256": digest,
        "migration_count": len(migrations),
    }


def inspect_runtime_schema() -> dict[str, Any]:
    query = """SELECT version FROM runtime_shared.schema_version
WHERE version IN ('001_i0011','002_i0012','003_i0013') ORDER BY version;
SELECT count(*) FROM information_schema.tables
WHERE table_schema IN ('runtime_shared','incident_owner','task_owner','graph_owner','action_owner','trace_buffer_owner');
"""
    encoded_query = base64.b64encode(query.encode()).decode()
    script = f"""set -eu
printf %s {encoded_query} | base64 -d | \
  /usr/local/bin/k3s kubectl -n fw-data exec -i postgres-0 -- sh -ec \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -At -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
"""
    output = [
        line.strip()
        for line in run_remote_script(script, privileged=True).splitlines()
        if line.strip()
    ]
    migrations = ["001_i0011", "002_i0012", "003_i0013"]
    if output[:3] != migrations or len(output) != 4 or int(output[3]) < 24:
        raise GovernanceError("runtime schema inventory is incomplete")
    return {
        "migrations": migrations,
        "table_count": int(output[3]),
    }
