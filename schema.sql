-- Agent CRM Schema
-- SQLite version (single-player)

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- Contacts
CREATE TABLE IF NOT EXISTS contacts (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name        TEXT NOT NULL,
    email       TEXT,
    phone       TEXT,
    company     TEXT,
    role        TEXT,
    source      TEXT,
    tags        TEXT,  -- JSON array
    notes       TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(name);
CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company);
CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);

-- Companies (denormalized from contacts, but useful for rollups)
CREATE TABLE IF NOT EXISTS companies (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name        TEXT NOT NULL UNIQUE,
    domain      TEXT,
    industry    TEXT,
    size        TEXT,
    notes       TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- Deals
CREATE TABLE IF NOT EXISTS deals (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    contact_id      TEXT REFERENCES contacts(id),
    company_id      TEXT REFERENCES companies(id),
    title           TEXT NOT NULL,
    value           REAL,
    currency        TEXT DEFAULT 'USD',
    stage           TEXT NOT NULL DEFAULT 'lead',
    probability     INTEGER,
    expected_close  TEXT,
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    closed_at       TEXT
);

CREATE INDEX IF NOT EXISTS idx_deals_stage ON deals(stage);
CREATE INDEX IF NOT EXISTS idx_deals_contact ON deals(contact_id);

-- Interactions
CREATE TABLE IF NOT EXISTS interactions (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    contact_id  TEXT REFERENCES contacts(id),
    deal_id     TEXT REFERENCES deals(id),
    type        TEXT NOT NULL,  -- email, call, meeting, note, linkedin, text
    direction   TEXT,           -- inbound, outbound
    summary     TEXT NOT NULL,
    raw_content TEXT,
    occurred_at TEXT NOT NULL,
    logged_at   TEXT DEFAULT (datetime('now')),
    logged_by   TEXT DEFAULT 'agent'
);

CREATE INDEX IF NOT EXISTS idx_interactions_contact ON interactions(contact_id);
CREATE INDEX IF NOT EXISTS idx_interactions_occurred ON interactions(occurred_at);

-- Tasks
CREATE TABLE IF NOT EXISTS tasks (
    id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    contact_id   TEXT REFERENCES contacts(id),
    deal_id      TEXT REFERENCES deals(id),
    title        TEXT NOT NULL,
    due_at       TEXT,
    completed_at TEXT,
    priority     TEXT DEFAULT 'normal',
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_at);
CREATE INDEX IF NOT EXISTS idx_tasks_completed ON tasks(completed_at);

-- Audit Log
CREATE TABLE IF NOT EXISTS audit_log (
    id               TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    table_name       TEXT NOT NULL,
    record_id        TEXT NOT NULL,
    action           TEXT NOT NULL,  -- INSERT, UPDATE, DELETE
    old_values       TEXT,           -- JSON
    new_values       TEXT,           -- JSON
    reason           TEXT,
    conversation_ref TEXT,
    created_at       TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_record ON audit_log(table_name, record_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
