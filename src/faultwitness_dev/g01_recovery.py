"""Candidate-bound, project-scoped G01 recovery rehearsals."""

from __future__ import annotations

import base64
import re
from typing import Any

from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.infra import run_remote_script

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def run_postgres_restore_rehearsal(candidate_sha: str) -> dict[str, Any]:
    """Restore the project database into a fresh temporary target and compare digests."""
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    inner = r"""set -eu
target=fw_g01_restore_eval
dump=/tmp/fw-g01-restore.dump
source_schema=/tmp/fw-g01-source-schema.sql
target_schema=/tmp/fw-g01-target-schema.sql
source_data=/tmp/fw-g01-source-data.sql
target_data=/tmp/fw-g01-target-data.sql
cleanup() {
  PGPASSWORD="$POSTGRES_PASSWORD" dropdb -U "$POSTGRES_USER" \
    --if-exists "$target" >/dev/null 2>&1 || true
  rm -f "$dump" "$source_schema" "$target_schema" "$source_data" "$target_data"
}
trap cleanup EXIT HUP INT TERM
cleanup
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$dump"
PGPASSWORD="$POSTGRES_PASSWORD" createdb -U "$POSTGRES_USER" "$target"
PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -U "$POSTGRES_USER" -d "$target" --exit-on-error "$dump"
for mode in schema data; do
  if test "$mode" = schema; then
    flags='--schema-only'
  else
    flags='--data-only --inserts'
  fi
  PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --no-owner --no-privileges $flags | \
    sed '/^\\restrict /d;/^\\unrestrict /d' >"/tmp/fw-g01-source-$mode.sql"
  PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$target" \
    --no-owner --no-privileges $flags | \
    sed '/^\\restrict /d;/^\\unrestrict /d' >"/tmp/fw-g01-target-$mode.sql"
done
source_schema_sha=$(sha256sum "$source_schema" | awk '{print $1}')
target_schema_sha=$(sha256sum "$target_schema" | awk '{print $1}')
source_data_sha=$(sha256sum "$source_data" | awk '{print $1}')
target_data_sha=$(sha256sum "$target_data" | awk '{print $1}')
test "$source_schema_sha" = "$target_schema_sha"
test "$source_data_sha" = "$target_data_sha"
printf '%s\n%s\n' "$source_schema_sha" "$source_data_sha"
"""
    encoded = base64.b64encode(inner.encode()).decode()
    script = f"""set -eu
binding=$(/usr/local/bin/k3s kubectl -n fw-system get configmap \
  fw-runtime-candidate-binding -o jsonpath='{{.data.candidate_sha}}')
test "$binding" = {candidate_sha}
printf %s {encoded} | base64 -d | \
  /usr/local/bin/k3s kubectl -n fw-data exec -i postgres-0 -- sh -s
"""
    lines = [
        line.strip()
        for line in run_remote_script(script, privileged=True, timeout=300).splitlines()
        if line.strip()
    ]
    if len(lines) != 2 or any(
        len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest)
        for digest in lines
    ):
        raise GovernanceError("PostgreSQL restore rehearsal returned invalid sanitized digests")
    return {
        "candidate_sha": candidate_sha,
        "status": "pass",
        "fresh_target": True,
        "schema_sha256": lines[0],
        "data_sha256": lines[1],
        "temporary_target_removed": True,
    }
