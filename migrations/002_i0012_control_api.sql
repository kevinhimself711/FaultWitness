BEGIN;

CREATE TABLE IF NOT EXISTS incident_owner.incident (
  tenant_id text NOT NULL,
  incident_id text NOT NULL,
  state text NOT NULL,
  state_version bigint NOT NULL CHECK (state_version >= 0),
  event_cursor bigint NOT NULL CHECK (event_cursor >= 0),
  final_report_ref text,
  spec jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, incident_id)
);

CREATE TABLE IF NOT EXISTS incident_owner.api_idempotency (
  tenant_id text NOT NULL,
  operation text NOT NULL,
  idempotency_key text NOT NULL,
  request_digest text NOT NULL,
  response jsonb NOT NULL,
  http_status integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, operation, idempotency_key)
);

CREATE TABLE IF NOT EXISTS incident_owner.event_projection (
  tenant_id text NOT NULL,
  incident_id text NOT NULL,
  sequence bigint NOT NULL CHECK (sequence > 0),
  event_id text NOT NULL,
  event_type text NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  payload jsonb NOT NULL,
  PRIMARY KEY (tenant_id, incident_id, sequence),
  UNIQUE (event_id),
  FOREIGN KEY (tenant_id, incident_id)
    REFERENCES incident_owner.incident(tenant_id, incident_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS incident_projection_retention
  ON incident_owner.event_projection(tenant_id, incident_id, occurred_at, sequence);

CREATE TABLE IF NOT EXISTS incident_owner.feedback (
  feedback_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  incident_id text NOT NULL,
  user_id text NOT NULL,
  rating integer NOT NULL CHECK (rating BETWEEN 1 AND 5),
  comment text,
  accepted_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, incident_id)
    REFERENCES incident_owner.incident(tenant_id, incident_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS incident_owner.pending_approval (
  tenant_id text NOT NULL,
  incident_id text NOT NULL,
  action_id text NOT NULL,
  action_digest text NOT NULL CHECK (action_digest ~ '^[0-9a-f]{64}$'),
  state_version bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, incident_id, action_id),
  FOREIGN KEY (tenant_id, incident_id)
    REFERENCES incident_owner.incident(tenant_id, incident_id) ON DELETE RESTRICT
);

INSERT INTO runtime_shared.schema_version(version) VALUES ('002_i0012') ON CONFLICT DO NOTHING;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA incident_owner TO fw_incident_owner;

COMMIT;
