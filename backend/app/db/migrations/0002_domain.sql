-- Domain stores. Rupee amounts are TEXT (Decimal-as-string, matching the
-- dataclasses) -- never numeric/float round-trips. Snapshot documents
-- (exceptions, close items, review flags) live as JSONB because they are
-- loaded/mutated/saved whole, mirroring the file-store semantics.

CREATE TABLE reports (
    report_id text PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES orgs(org_id),
    client_name text NOT NULL,
    created_at text NOT NULL,
    period_note text NOT NULL DEFAULT '',
    matched_count int NOT NULL,
    matched_tax_total text NOT NULL,
    exceptions jsonb NOT NULL,
    missed_itc jsonb NOT NULL,
    unresolved jsonb NOT NULL
);
CREATE INDEX reports_org_created_idx ON reports (org_id, created_at DESC);

CREATE TABLE bank_reports (
    report_id text PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES orgs(org_id),
    client_name text NOT NULL,
    created_at text NOT NULL,
    period_note text NOT NULL DEFAULT '',
    matched_count int NOT NULL,
    matched_total text NOT NULL,
    unrecorded jsonb NOT NULL,
    uncleared jsonb NOT NULL
);
CREATE INDEX bank_reports_org_created_idx ON bank_reports (org_id, created_at DESC);

CREATE TABLE close_workbooks (
    org_id uuid NOT NULL REFERENCES orgs(org_id),
    period text NOT NULL CHECK (period ~ '^\d{4}-\d{2}$'),
    created_at text NOT NULL,
    items jsonb NOT NULL,
    PRIMARY KEY (org_id, period)
);

CREATE TABLE invoices (
    invoice_id text PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES orgs(org_id),
    period text NOT NULL,
    created_at text NOT NULL,
    status text NOT NULL CHECK (status IN ('draft', 'confirmed')),
    source_file text NOT NULL,
    scan bytea NOT NULL,
    scan_mime text NOT NULL,
    extraction text NOT NULL,
    fields jsonb NOT NULL,
    extraction_note text NOT NULL DEFAULT '',
    confirmed_by text NOT NULL DEFAULT '',
    confirmed_at text NOT NULL DEFAULT '',
    ca_signoff text NOT NULL DEFAULT ''
);
CREATE INDEX invoices_org_period_status_idx ON invoices (org_id, period, status);

CREATE TABLE coa_accounts (
    org_id uuid NOT NULL REFERENCES orgs(org_id),
    code text NOT NULL,
    name text NOT NULL,
    type text NOT NULL,
    PRIMARY KEY (org_id, code)
);

CREATE TABLE categorization_rules (
    org_id uuid NOT NULL REFERENCES orgs(org_id),
    rule_id text NOT NULL,
    priority int NOT NULL,
    field text NOT NULL,
    contains text NOT NULL,
    account_code text NOT NULL,
    created_by text NOT NULL,
    created_at text NOT NULL,
    PRIMARY KEY (org_id, rule_id)
);
CREATE UNIQUE INDEX categorization_rules_dedupe
    ON categorization_rules (org_id, field, lower(contains));

CREATE TABLE ledgers (
    org_id uuid NOT NULL REFERENCES orgs(org_id),
    period text NOT NULL CHECK (period ~ '^\d{4}-\d{2}$'),
    created_at text NOT NULL,
    PRIMARY KEY (org_id, period)
);

CREATE TABLE ledger_txns (
    org_id uuid NOT NULL,
    period text NOT NULL,
    txn_id text NOT NULL,
    txn_date text NOT NULL,
    description text NOT NULL,
    ref text NOT NULL DEFAULT '',
    amount text NOT NULL,
    source_ref text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'coded', 'confirmed')),
    source text NOT NULL DEFAULT '',
    account_code text NOT NULL DEFAULT '',
    rule_id text NOT NULL DEFAULT '',
    suggested_account text NOT NULL DEFAULT '',
    confidence text NOT NULL DEFAULT '',
    confirmed_by text NOT NULL DEFAULT '',
    confirmed_at text NOT NULL DEFAULT '',
    PRIMARY KEY (org_id, period, txn_id),
    FOREIGN KEY (org_id, period) REFERENCES ledgers (org_id, period)
);
CREATE UNIQUE INDEX ledger_txns_dedupe
    ON ledger_txns (org_id, period, txn_date, lower(btrim(description)), ref, amount);

CREATE TABLE review_workbooks (
    org_id uuid NOT NULL REFERENCES orgs(org_id),
    period text NOT NULL CHECK (period ~ '^\d{4}-\d{2}$'),
    prior_period text NOT NULL,
    created_at text NOT NULL,
    pnl jsonb NOT NULL,
    summary jsonb NOT NULL,
    flags jsonb NOT NULL,
    txn_counts jsonb NOT NULL,
    narrative text NOT NULL DEFAULT '',
    narrative_note text NOT NULL DEFAULT '',
    PRIMARY KEY (org_id, period)
);
