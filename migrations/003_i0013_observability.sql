BEGIN;

CREATE SCHEMA IF NOT EXISTS trace_buffer_owner;

DO $roles$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fw_trace_owner') THEN
    CREATE ROLE fw_trace_owner NOLOGIN;
  END IF;
END $roles$;

CREATE TABLE IF NOT EXISTS trace_buffer_owner.trace_payload (
  trace_ref text PRIMARY KEY CHECK (trace_ref ~ '^[0-9a-f]{24}$'),
  payload_digest text NOT NULL CHECK (payload_digest ~ '^[0-9a-f]{64}$'),
  key_id text NOT NULL,
  nonce bytea NOT NULL CHECK (octet_length(nonce) = 12),
  ciphertext bytea NOT NULL,
  format_version integer NOT NULL CHECK (format_version = 1),
  candidate_sha text NOT NULL CHECK (candidate_sha ~ '^[0-9a-f]{40}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (trace_ref, payload_digest)
);

CREATE TABLE IF NOT EXISTS trace_buffer_owner.delivery (
  trace_ref text NOT NULL REFERENCES trace_buffer_owner.trace_payload(trace_ref) ON DELETE RESTRICT,
  sink text NOT NULL CHECK (sink IN ('langsmith','otlp','archive')),
  state text NOT NULL CHECK (state IN ('PENDING','LEASED','ACKED')),
  attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  next_attempt_at timestamptz NOT NULL DEFAULT now(),
  leased_until timestamptz,
  acked_at timestamptz,
  last_error_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (trace_ref, sink),
  CHECK ((state = 'LEASED') = (leased_until IS NOT NULL)),
  CHECK ((state = 'ACKED') = (acked_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS trace_delivery_ready
  ON trace_buffer_owner.delivery(sink, state, next_attempt_at, created_at);

REVOKE ALL ON SCHEMA trace_buffer_owner FROM PUBLIC;
GRANT USAGE ON SCHEMA trace_buffer_owner TO fw_trace_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA trace_buffer_owner TO fw_trace_owner;

INSERT INTO runtime_shared.schema_version(version)
VALUES ('003_i0013') ON CONFLICT DO NOTHING;

COMMIT;
