-- Append-only agent event log. UPDATE/DELETE rejected at the database,
-- mirroring the SQLite triggers this replaces (marketed product guarantee).

CREATE TABLE agent_events (
    event_id bigserial PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES orgs(org_id),
    agent text NOT NULL,
    action text NOT NULL,
    input_doc_ref text NOT NULL DEFAULT '',
    output_ref text NOT NULL DEFAULT '',
    actor text NOT NULL DEFAULT '',
    reviewed_by text NOT NULL DEFAULT '',
    ts timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION agent_events_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'agent_events is append-only';
END
$$;

CREATE TRIGGER agent_events_no_update BEFORE UPDATE ON agent_events
    FOR EACH ROW EXECUTE FUNCTION agent_events_immutable();
CREATE TRIGGER agent_events_no_delete BEFORE DELETE ON agent_events
    FOR EACH ROW EXECUTE FUNCTION agent_events_immutable();

CREATE INDEX agent_events_org_output_idx ON agent_events (org_id, output_ref, event_id);
CREATE INDEX agent_events_org_recent_idx ON agent_events (org_id, event_id DESC);
