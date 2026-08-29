CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE users (
    user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email citext UNIQUE NOT NULL,
    password_hash text NOT NULL,
    display_name text NOT NULL,
    ca_membership_no text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE orgs (
    org_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE memberships (
    user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    org_id uuid NOT NULL REFERENCES orgs(org_id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('owner', 'preparer', 'reviewer', 'viewer')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, org_id)
);
CREATE INDEX memberships_org_idx ON memberships (org_id);

CREATE TABLE sessions (
    session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash text UNIQUE NOT NULL,
    user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE invites (
    invite_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL REFERENCES orgs(org_id) ON DELETE CASCADE,
    token_hash text UNIQUE NOT NULL,
    role text NOT NULL CHECK (role IN ('preparer', 'reviewer', 'viewer')),
    email text NOT NULL DEFAULT '',
    created_by uuid NOT NULL REFERENCES users(user_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    accepted_by uuid REFERENCES users(user_id),
    accepted_at timestamptz
);
CREATE INDEX invites_org_idx ON invites (org_id);
