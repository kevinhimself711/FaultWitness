# ruff: noqa: E501 -- remote shell commands stay literal for auditability.

from __future__ import annotations

import base64
import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.infra import run_remote_script

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def deploy_runtime_schema(root: Path, candidate_sha: str) -> dict[str, Any]:
    migrations = sorted((root / "migrations").glob("*.sql"))
    if not migrations:
        raise GovernanceError("runtime migrations are absent")
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    if head != candidate_sha:
        raise GovernanceError("candidate SHA does not match repository HEAD")
    dirty = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            *(str(migration.relative_to(root)) for migration in migrations),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if dirty.strip():
        raise GovernanceError("runtime migration differs from immutable candidate")
    payload = b"\n".join(migration.read_bytes() for migration in migrations)
    encoded = base64.b64encode(payload).decode()
    digest = hashlib.sha256(payload).hexdigest()
    script = f"""set -eu
work=$(mktemp -d /tmp/faultwitness-i0011.XXXXXX)
trap 'rm -rf "$work"' EXIT HUP INT TERM
printf %s {encoded} | base64 -d >"$work/migration.sql"
test "$(sha256sum "$work/migration.sql" | awk '{{print $1}}')" = {digest}
/usr/local/bin/k3s kubectl -n fw-data cp "$work/migration.sql" postgres-0:/tmp/fw-migration.sql
/usr/local/bin/k3s kubectl -n fw-data exec postgres-0 -- sh -ec \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/fw-migration.sql >/dev/null'
/usr/local/bin/k3s kubectl -n fw-data exec postgres-0 -- rm -f /tmp/fw-migration.sql
/usr/local/bin/k3s kubectl -n fw-system create configmap fw-runtime-candidate-binding \
  --from-literal=candidate_sha={candidate_sha} --from-literal=migration_sha256={digest} \
  --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f - >/dev/null
"""
    run_remote_script(script, privileged=True, timeout=180)
    return {
        "candidate_sha": candidate_sha,
        "migration_sha256": digest,
        "migration_count": len(migrations),
    }


def inspect_runtime_schema(candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    query = """SELECT version FROM runtime_shared.schema_version
WHERE version IN ('001_i0011','002_i0012','003_i0013') ORDER BY version;
SELECT count(*) FROM information_schema.tables
WHERE table_schema IN ('runtime_shared','incident_owner','task_owner','graph_owner','action_owner','trace_buffer_owner');
"""
    encoded_query = base64.b64encode(query.encode()).decode()
    script = f"""set -eu
binding=$(/usr/local/bin/k3s kubectl -n fw-system get configmap fw-runtime-candidate-binding -o jsonpath='{{.data.candidate_sha}}')
test "$binding" = {candidate_sha}
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
        "candidate_sha": candidate_sha,
        "migrations": migrations,
        "table_count": int(output[3]),
    }
