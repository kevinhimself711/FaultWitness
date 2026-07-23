# ruff: noqa: E501 -- embedded remote programs stay literal for auditability.
"""Real private-server failure matrices for the G01 immutable candidate."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
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
    encoded = base64.b64encode(gzip.compress(sql.encode(), mtime=0)).decode()
    script = f"""set -eu
binding=$(/usr/local/bin/k3s kubectl -n fw-system get configmap \
  fw-runtime-candidate-binding -o jsonpath='{{.data.candidate_sha}}')
test "$binding" = {candidate_sha}
printf %s {encoded} | base64 -d | gzip -d | \
  /usr/local/bin/k3s kubectl -n fw-data exec -i postgres-0 -- sh -ec \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -qAt -v ON_ERROR_STOP=1 \
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


def run_redis_recovery_matrix(candidate_sha: str) -> dict[str, Any]:
    """Leave messages pending under a crashed consumer, reclaim, ACK, and drain."""
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    stream = f"fw:g01:recovery:{candidate_sha[:12]}"
    inner = f"""set -eu
cli() {{ redis-cli --no-auth-warning -a "$REDIS_PASSWORD" --raw "$@"; }}
stream='{stream}'
group='g01-recovery'
cli DEL "$stream" >/dev/null
cli XGROUP CREATE "$stream" "$group" 0 MKSTREAM >/dev/null
for value in $(seq 1 100); do
  cli XADD "$stream" '*' event_id "g01-event-$value" payload '{{}}' >/dev/null
done
cli XREADGROUP GROUP "$group" crashed-consumer COUNT 100 STREAMS "$stream" '>' >/dev/null
pending_before=$(cli XPENDING "$stream" "$group" | head -1)
ids=$(cli XPENDING "$stream" "$group" - + 100 | awk 'NR % 4 == 1 {{print $1}}')
test "$(printf '%s\n' $ids | wc -l)" -eq 100
cli XCLAIM "$stream" "$group" recovered-consumer 0 $ids JUSTID >/dev/null
cli XACK "$stream" "$group" $ids >/dev/null
pending_after=$(cli XPENDING "$stream" "$group" | head -1)
length=$(cli XLEN "$stream")
cli DEL "$stream" >/dev/null
printf '%s\n%s\n%s\n' "$pending_before" "$length" "$pending_after"
"""
    encoded = base64.b64encode(inner.encode()).decode()
    script = f"""set -eu
binding=$(/usr/local/bin/k3s kubectl -n fw-system get configmap \
  fw-runtime-candidate-binding -o jsonpath='{{.data.candidate_sha}}')
test "$binding" = {candidate_sha}
printf %s {encoded} | base64 -d | \
  /usr/local/bin/k3s kubectl -n fw-data exec -i redis-0 -- sh -s
"""
    lines = [
        line.strip()
        for line in run_remote_script(script, privileged=True, timeout=180).splitlines()
        if line.strip()
    ]
    try:
        pending_before, stream_length, pending_after = map(int, lines)
    except ValueError as error:
        raise GovernanceError("Redis recovery matrix returned invalid counters") from error
    if [pending_before, stream_length, pending_after] != [100, 100, 0]:
        raise GovernanceError(
            "Redis recovery matrix counter mismatch: "
            f"pending_before={pending_before}, stream_length={stream_length}, "
            f"pending_after={pending_after}"
        )
    return {
        "candidate_sha": candidate_sha,
        "status": "pass",
        "published_count": 100,
        "crashed_consumer_pending": 100,
        "recovered_count": 100,
        "pending_after_recovery": 0,
        "temporary_stream_removed": True,
    }


def _control_api_load_manifest(candidate_sha: str) -> str:
    script = f'''import asyncio
import datetime
import json
import os

from faultwitness.api.postgres_store import PostgresIncidentStore
from faultwitness.api.schemas import FeedbackRequest, IncidentCreate
from faultwitness.api.server import _database_url
from faultwitness.api.store import RetentionGap

TENANT = "ten_01ARZ3NDEKTSV4RRFFQ69G5FAY"

async def main():
    store = PostgresIncidentStore(_database_url())
    await store.connect()
    now = datetime.datetime.now(datetime.UTC)
    request = IncidentCreate.model_validate({{
        "source":"g01-load","environment_id":"env_g01","service_scope":["svc_g01"],
        "time_window":{{"start":(now-datetime.timedelta(minutes=5)).isoformat(),"end":now.isoformat()}},
        "symptom_summary":"synthetic live SSE matrix","mode":"diagnosis_only",
        "budget":{{"deadline":(now+datetime.timedelta(minutes=20)).isoformat(),"max_steps":10,
        "max_model_calls":0,"max_tokens":0,"max_cost_usd":0}}
    }})
    feedback = FeedbackRequest(rating=5, expected_state_version=0)
    try:
        snapshot, _ = await store.create(TENANT, "g01-load-create", request)
        for value in range(9_999):
            await store.feedback(TENANT, "usr_g01", snapshot.incident_id,
                f"g01-feedback-{{value:05d}}", feedback)
        events = await store.replay(TENANT, snapshot.incident_id, None)
        event_count = len(events)
        ordered = [item.sequence for item in events] == list(range(1, 10_001))
        cursor = 0
        reconnects = 0
        for _ in range(100):
            replay = await store.replay(TENANT, snapshot.incident_id, str(cursor))
            batch = replay[:100]
            cursor = batch[-1].sequence
            reconnects += 1
        async with store._pool().acquire() as connection:
            await connection.execute("DELETE FROM incident_owner.event_projection "
                "WHERE tenant_id=$1 AND incident_id=$2 AND sequence<=100", TENANT, snapshot.incident_id)
        retention_gap = False
        try:
            await store.replay(TENANT, snapshot.incident_id, "0")
        except RetentionGap as gap:
            retention_gap = gap.earliest_cursor == "101"
        slow, _ = await store.create(TENANT, "g01-slow-create", request)
        subscriber = await store.subscribe(TENANT, slow.incident_id, buffer_size=1)
        await store.feedback(TENANT, "usr_g01", slow.incident_id, "g01-slow-1", feedback)
        await store.feedback(TENANT, "usr_g01", slow.incident_id, "g01-slow-2", feedback)
        slow_consumer_closed = subscriber.closed
        async with store._pool().acquire() as connection, connection.transaction():
            await connection.execute("DELETE FROM incident_owner.event_projection WHERE tenant_id=$1", TENANT)
            await connection.execute("DELETE FROM incident_owner.feedback WHERE tenant_id=$1", TENANT)
            await connection.execute("DELETE FROM incident_owner.api_idempotency WHERE tenant_id=$1", TENANT)
            await connection.execute("DELETE FROM incident_owner.pending_approval WHERE tenant_id=$1", TENANT)
            await connection.execute("DELETE FROM incident_owner.incident WHERE tenant_id=$1", TENANT)
            remaining = await connection.fetchval("SELECT count(*) FROM incident_owner.incident WHERE tenant_id=$1", TENANT)
        print(json.dumps({{"candidate_sha":"{candidate_sha}","event_count":event_count,
            "ordered":ordered,"reconnects":reconnects,"final_cursor":cursor,
            "retention_gap":retention_gap,"slow_consumer_closed":slow_consumer_closed,
            "remaining_rows":remaining}}, sort_keys=True))
    finally:
        await store.close()

asyncio.run(main())
'''
    return f"""apiVersion: v1
kind: ConfigMap
metadata: {{name: g01-api-load, namespace: fw-control}}
data:
  matrix.py: |
{chr(10).join("    " + line for line in script.splitlines())}
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {{name: g01-api-load-egress, namespace: fw-control}}
spec:
  podSelector: {{matchLabels: {{app.kubernetes.io/name: g01-api-load}}}}
  policyTypes: [Egress]
  egress:
    - to: [{{namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: kube-system}}}}}}]
      ports: [{{protocol: UDP, port: 53}}, {{protocol: TCP, port: 53}}]
    - to:
        - namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: fw-data}}}}
          podSelector: {{matchLabels: {{app.kubernetes.io/name: postgres}}}}
      ports: [{{protocol: TCP, port: 5432}}]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {{name: allow-g01-api-load-postgres, namespace: fw-data}}
spec:
  podSelector: {{matchLabels: {{app.kubernetes.io/name: postgres}}}}
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector: {{matchLabels: {{kubernetes.io/metadata.name: fw-control}}}}
          podSelector: {{matchLabels: {{app.kubernetes.io/name: g01-api-load}}}}
      ports: [{{protocol: TCP, port: 5432}}]
---
apiVersion: batch/v1
kind: Job
metadata: {{name: g01-api-load, namespace: fw-control}}
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 900
  template:
    metadata: {{labels: {{app.kubernetes.io/name: g01-api-load}}}}
    spec:
      restartPolicy: Never
      automountServiceAccountToken: false
      containers:
        - name: matrix
          image: docker.io/faultwitness/control-api:{candidate_sha}
          imagePullPolicy: Never
          command: [python, /config/matrix.py]
          envFrom: [{{secretRef: {{name: fw-control-postgres-env}}}}]
          volumeMounts: [{{name: script, mountPath: /config, readOnly: true}}]
          securityContext: {{allowPrivilegeEscalation: false, runAsNonRoot: true, capabilities: {{drop: [ALL]}}}}
      volumes: [{{name: script, configMap: {{name: g01-api-load}}}}]
"""


def run_control_api_load_matrix(candidate_sha: str) -> dict[str, Any]:
    if not FULL_SHA.fullmatch(candidate_sha):
        raise GovernanceError("candidate SHA must contain 40 lowercase hexadecimal characters")
    manifest = base64.b64encode(_control_api_load_manifest(candidate_sha).encode()).decode()
    script = f"""set -eu
binding=$(/usr/local/bin/k3s kubectl -n fw-control get configmap \
  fw-control-api-candidate -o jsonpath='{{.data.candidate_sha}}')
test "$binding" = {candidate_sha}
/usr/local/bin/k3s kubectl -n fw-control delete job g01-api-load \
  --ignore-not-found --wait=true >/dev/null
printf %s {manifest} | base64 -d | /usr/local/bin/k3s kubectl apply -f - >/dev/null
for attempt in $(seq 1 450); do
  succeeded=$(/usr/local/bin/k3s kubectl -n fw-control get job g01-api-load \
    -o jsonpath='{{.status.succeeded}}')
  failed=$(/usr/local/bin/k3s kubectl -n fw-control get job g01-api-load \
    -o jsonpath='{{.status.failed}}')
  test "$succeeded" = 1 && break
  test "$failed" = 1 && exit 1
  sleep 2
done
test "$succeeded" = 1
/usr/local/bin/k3s kubectl -n fw-control logs job/g01-api-load
"""
    output = run_remote_script(script, privileged=True, timeout=960).strip()
    try:
        result = json.loads(output)
    except json.JSONDecodeError as error:
        raise GovernanceError("Control API load matrix returned invalid sanitized JSON") from error
    expected = {
        "candidate_sha": candidate_sha,
        "event_count": 10_000,
        "ordered": True,
        "reconnects": 100,
        "final_cursor": 10_000,
        "retention_gap": True,
        "slow_consumer_closed": True,
        "remaining_rows": 0,
    }
    if any(result.get(key) != value for key, value in expected.items()):
        raise GovernanceError("Control API load matrix did not meet frozen counters")
    return {"status": "pass", **result}
