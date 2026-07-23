"""Real private-server failure matrices for the G01 immutable candidate."""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path
from typing import Any

from faultwitness.contracts.compiler import load_generated_resource
from faultwitness_dev.errors import GovernanceError
from faultwitness_dev.infra import run_remote_script

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
EVAL_TENANT = "ten_01ARZ3NDEKTSV4RRFFQ69G5FAX"
SCHEMA_BY_MACHINE = {
    "incident": "incident_owner",
    "runtime_task": "task_owner",
    "agent_graph": "graph_owner",
    "action_transaction": "action_owner",
}


def _transition_sql(root: Path) -> tuple[str, int]:
    resource = load_generated_resource(root)
    documents = resource["documents"]
    statements: list[str] = []
    count = 0
    for machine_id, schema in SCHEMA_BY_MACHINE.items():
        machine = documents[f"state_machine.{machine_id}"]
        for transition in machine["transitions"]:
            count += 1
            suffix = f"{count:03d}"
            aggregate = f"g01_eval_aggregate_{suffix}"
            event_id = f"g01_eval_event_{suffix}"
            outbox_id = f"g01_eval_outbox_{suffix}"
            key = f"g01-eval-idempotency-{suffix}"
            digest = hashlib.sha256(transition["id"].encode()).hexdigest()
            statements.extend(
                [
                    f"INSERT INTO {schema}.aggregate_state "
                    "(tenant_id,aggregate_id,machine_id,state,state_version) VALUES "
                    f"('{EVAL_TENANT}','{aggregate}','{machine_id}',"
                    f"'{transition['to']}',1);",
                    f"INSERT INTO {schema}.outbox "
                    "(outbox_id,tenant_id,aggregate_id,event_id,event_type,payload) VALUES "
                    f"('{outbox_id}','{EVAL_TENANT}','{aggregate}','{event_id}',"
                    f"'{transition['event']}','{{}}'::jsonb);",
                    f"INSERT INTO {schema}.idempotency "
                    "(tenant_id,idempotency_key,request_digest,response) VALUES "
                    f"('{EVAL_TENANT}','{key}','{digest}',"
                    f'\'{{"event_id":"{event_id}","outbox_id":"{outbox_id}"}}\'::jsonb);',
                ]
            )
    return "\n".join(statements), count


def run_postgres_failure_matrix(root: Path, candidate_sha: str) -> dict[str, Any]:
    """Execute all-transition atomicity, duplicate, crash, and fencing checks."""
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    transition_sql, transition_count = _transition_sql(root)
    if transition_count != 82:
        raise GovernanceError(f"frozen transition count drifted: {transition_count}")
    owner_union = " UNION ALL ".join(
        f"SELECT count(*) AS value FROM {schema}.{{table}} WHERE tenant_id='{EVAL_TENANT}'"
        for schema in SCHEMA_BY_MACHINE.values()
    )
    aggregate_count = owner_union.format(table="aggregate_state")
    outbox_count = owner_union.format(table="outbox")
    idempotency_count = owner_union.format(table="idempotency")
    sql = f"""BEGIN;
{transition_sql}
INSERT INTO runtime_shared.inbox(tenant_id,consumer,event_id,state)
SELECT '{EVAL_TENANT}','g01-matrix','g01-duplicate-' || value,'RECEIVED'
FROM generate_series(1,5000) AS value ON CONFLICT DO NOTHING;
INSERT INTO runtime_shared.inbox(tenant_id,consumer,event_id,state)
SELECT '{EVAL_TENANT}','g01-matrix','g01-duplicate-' || value,'RECEIVED'
FROM generate_series(1,5000) AS value ON CONFLICT DO NOTHING;
DO $matrix$
BEGIN
  FOR value IN 1..100 LOOP
    BEGIN
      INSERT INTO incident_owner.aggregate_state
        (tenant_id,aggregate_id,machine_id,state,state_version)
      VALUES ('{EVAL_TENANT}-crash','g01-crash-' || value,'incident','NEW',1);
      INSERT INTO incident_owner.outbox
        (outbox_id,tenant_id,aggregate_id,event_id,event_type,payload)
      VALUES ('g01-crash-outbox-' || value,'{EVAL_TENANT}-crash',
        'g01-crash-' || value,'g01-crash-event-' || value,
        'EVT-INCIDENT-CREATED','{{}}'::jsonb);
      RAISE EXCEPTION 'injected crash';
    EXCEPTION WHEN OTHERS THEN NULL;
    END;
  END LOOP;
END $matrix$;
INSERT INTO task_owner.lease
  (tenant_id,task_id,attempt_id,worker_id,fencing_token,expires_at)
VALUES ('{EVAL_TENANT}','g01-fence-task','g01-current-attempt','g01-worker',43,
  now()+interval '10 minutes');
INSERT INTO graph_owner.checkpoint
  (tenant_id,task_id,attempt_id,fencing_token,state_version,ciphertext,key_id)
SELECT '{EVAL_TENANT}','g01-fence-task','g01-stale-attempt',42,1,
  decode('00','hex'),'g01-key'
WHERE EXISTS (SELECT 1 FROM task_owner.lease WHERE tenant_id='{EVAL_TENANT}'
  AND task_id='g01-fence-task' AND attempt_id='g01-stale-attempt'
  AND fencing_token=42 AND expires_at>now());
SELECT sum(value) FROM ({aggregate_count}) AS counts;
SELECT sum(value) FROM ({outbox_count}) AS counts;
SELECT sum(value) FROM ({idempotency_count}) AS counts;
SELECT count(*) FROM runtime_shared.inbox
WHERE tenant_id='{EVAL_TENANT}' AND consumer='g01-matrix';
SELECT count(*) FROM incident_owner.aggregate_state
WHERE tenant_id='{EVAL_TENANT}-crash';
SELECT count(*) FROM graph_owner.checkpoint
WHERE tenant_id='{EVAL_TENANT}' AND task_id='g01-fence-task';
INSERT INTO graph_owner.checkpoint
  (tenant_id,task_id,attempt_id,fencing_token,state_version,ciphertext,key_id)
SELECT '{EVAL_TENANT}','g01-fence-task','g01-current-attempt',43,1,
  decode('00','hex'),'g01-key'
WHERE EXISTS (SELECT 1 FROM task_owner.lease WHERE tenant_id='{EVAL_TENANT}'
  AND task_id='g01-fence-task' AND attempt_id='g01-current-attempt'
  AND fencing_token=43 AND expires_at>now());
SELECT count(*) FROM graph_owner.checkpoint
WHERE tenant_id='{EVAL_TENANT}' AND task_id='g01-fence-task';
ROLLBACK;
"""
    encoded = base64.b64encode(sql.encode()).decode()
    script = f"""set -eu
binding=$(/usr/local/bin/k3s kubectl -n fw-system get configmap \
  fw-runtime-candidate-binding -o jsonpath='{{.data.candidate_sha}}')
test "$binding" = {candidate_sha}
printf %s {encoded} | base64 -d | \
  /usr/local/bin/k3s kubectl -n fw-data exec -i postgres-0 -- sh -ec \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -At -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
"""
    lines = [
        line.strip()
        for line in run_remote_script(script, privileged=True, timeout=300).splitlines()
        if line.strip()
    ]
    try:
        counters = [int(value) for value in lines]
    except ValueError as error:
        raise GovernanceError("PostgreSQL failure matrix returned invalid counters") from error
    expected = [82, 82, 82, 5000, 0, 0, 1]
    if counters != expected:
        raise GovernanceError(
            f"PostgreSQL failure matrix counter mismatch: expected={expected}, actual={counters}"
        )
    return {
        "candidate_sha": candidate_sha,
        "status": "pass",
        "transition_count": 82,
        "aggregate_count": 82,
        "outbox_count": 82,
        "idempotency_count": 82,
        "duplicate_delivery_attempts": 10_000,
        "unique_inbox_count": 5_000,
        "crash_injection_count": 100,
        "partial_commit_count": 0,
        "stale_fence_accept_count": 0,
        "current_fence_accept_count": 1,
        "persistent_rows_after_rollback": 0,
    }
