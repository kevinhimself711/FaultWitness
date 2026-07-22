BEGIN;

CREATE SCHEMA IF NOT EXISTS runtime_shared;
CREATE SCHEMA IF NOT EXISTS incident_owner;
CREATE SCHEMA IF NOT EXISTS task_owner;
CREATE SCHEMA IF NOT EXISTS graph_owner;
CREATE SCHEMA IF NOT EXISTS action_owner;

DO $roles$
DECLARE service_role text;
BEGIN
  FOREACH service_role IN ARRAY ARRAY[
    'fw_incident_owner','fw_task_owner','fw_graph_owner','fw_action_owner','fw_event_relay'
  ] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = service_role) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN', service_role);
    END IF;
  END LOOP;
END $roles$;

CREATE TABLE IF NOT EXISTS runtime_shared.schema_version (
  version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO runtime_shared.schema_version(version) VALUES ('001_i0011') ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS runtime_shared.inbox (
  tenant_id text NOT NULL, consumer text NOT NULL, event_id text NOT NULL,
  state text NOT NULL CHECK (state IN ('RECEIVED','APPLIED','DUPLICATE_ACK','DEAD_LETTER')),
  received_at timestamptz NOT NULL DEFAULT now(), applied_at timestamptz,
  PRIMARY KEY (tenant_id, consumer, event_id)
);
CREATE TABLE IF NOT EXISTS runtime_shared.dead_letter (
  tenant_id text NOT NULL, consumer text NOT NULL, event_id text NOT NULL,
  reason text NOT NULL, payload bytea NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, consumer, event_id)
);

DO $migration$
DECLARE owner_schema text;
BEGIN
  FOREACH owner_schema IN ARRAY ARRAY['incident_owner','task_owner','graph_owner','action_owner']
  LOOP
    EXECUTE format('CREATE TABLE IF NOT EXISTS %I.aggregate_state (
      tenant_id text NOT NULL, aggregate_id text NOT NULL, machine_id text NOT NULL,
      state text NOT NULL, state_version bigint NOT NULL CHECK (state_version >= 0),
      updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, aggregate_id))', owner_schema);
    EXECUTE format('CREATE TABLE IF NOT EXISTS %I.idempotency (
      tenant_id text NOT NULL, idempotency_key text NOT NULL, request_digest text NOT NULL,
      response jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (tenant_id, idempotency_key))', owner_schema);
    EXECUTE format('CREATE TABLE IF NOT EXISTS %I.outbox (
      outbox_id text PRIMARY KEY, tenant_id text NOT NULL, aggregate_id text NOT NULL,
      event_id text NOT NULL UNIQUE, event_type text NOT NULL, payload jsonb NOT NULL,
      state text NOT NULL DEFAULT ''PENDING'' CHECK (state IN (''PENDING'',''CLAIMED'',''PUBLISHED'')),
      attempt_count integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(),
      claimed_until timestamptz, published_at timestamptz)', owner_schema);
    EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I.outbox(state,available_at)', owner_schema || '_outbox_ready', owner_schema);
  END LOOP;
END $migration$;

CREATE TABLE IF NOT EXISTS task_owner.lease (
  tenant_id text NOT NULL, task_id text NOT NULL, attempt_id text NOT NULL,
  worker_id text NOT NULL, fencing_token bigint NOT NULL CHECK (fencing_token >= 0),
  expires_at timestamptz NOT NULL, PRIMARY KEY (tenant_id, task_id)
);
CREATE TABLE IF NOT EXISTS graph_owner.checkpoint (
  tenant_id text NOT NULL, task_id text NOT NULL, attempt_id text NOT NULL,
  fencing_token bigint NOT NULL, state_version bigint NOT NULL,
  ciphertext bytea NOT NULL, key_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, task_id)
);

REVOKE ALL ON SCHEMA incident_owner, task_owner, graph_owner, action_owner FROM PUBLIC;
GRANT USAGE ON SCHEMA incident_owner TO fw_incident_owner;
GRANT USAGE ON SCHEMA task_owner TO fw_task_owner;
GRANT USAGE ON SCHEMA graph_owner TO fw_graph_owner;
GRANT USAGE ON SCHEMA action_owner TO fw_action_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA incident_owner TO fw_incident_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA task_owner TO fw_task_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA graph_owner TO fw_graph_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA action_owner TO fw_action_owner;
GRANT SELECT, UPDATE ON ALL TABLES IN SCHEMA incident_owner, task_owner, graph_owner, action_owner TO fw_event_relay;

COMMIT;
