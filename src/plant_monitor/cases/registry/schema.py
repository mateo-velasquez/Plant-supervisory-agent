"""SQLite schema and its version."""

from typing import Final

SCHEMA_VERSION: Final = 2

SCHEMA: Final = f"""
BEGIN;
CREATE TABLE processed_snapshots (
    snapshot_id  TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    seq          INTEGER NOT NULL UNIQUE
);
CREATE TABLE anomalies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    detail      TEXT NOT NULL,
    UNIQUE (kind, snapshot_id, detail)
);
CREATE TABLE known_units (
    unidad_id TEXT PRIMARY KEY,
    modelo    TEXT NOT NULL,
    mercado   TEXT NOT NULL
);
CREATE TABLE released_units (
    seq         INTEGER NOT NULL,
    idx         INTEGER NOT NULL,
    snapshot_id TEXT NOT NULL,
    unidad_id   TEXT NOT NULL,
    modelo      TEXT NOT NULL,
    mercado     TEXT NOT NULL,
    hora        TEXT NOT NULL,
    PRIMARY KEY (seq, idx)
);
CREATE TABLE cases (
    case_id                   TEXT PRIMARY KEY,
    modelo                    TEXT NOT NULL,
    mercado                   TEXT NOT NULL,
    opened_at                 TEXT NOT NULL,
    state                     TEXT NOT NULL,
    minimum_severity          TEXT NOT NULL,
    raised                    INTEGER NOT NULL,
    current_severity          TEXT NOT NULL,
    max_severity_since_report TEXT,
    clean_streak              INTEGER NOT NULL,
    last_snapshot_id          TEXT NOT NULL,
    last_reported_at          TEXT,
    last_reported_state       TEXT,
    last_reported_severity    TEXT,
    resolved_at               TEXT
);
CREATE UNIQUE INDEX one_active_case_per_combination
    ON cases (modelo, mercado) WHERE state <> 'resuelto';
CREATE TABLE case_history (
    case_id            TEXT NOT NULL REFERENCES cases (case_id),
    snapshot_id        TEXT NOT NULL,
    seq                INTEGER NOT NULL,
    state              TEXT NOT NULL,
    minimum_severity   TEXT NOT NULL,
    raised             INTEGER NOT NULL,
    effective_severity TEXT NOT NULL,
    gap_units          REAL NOT NULL,
    gap_pct            REAL,
    delay_days         REAL,
    bottleneck         TEXT,
    clean_streak       INTEGER NOT NULL,
    PRIMARY KEY (case_id, snapshot_id)
);
CREATE TABLE notices (
    notice_id    TEXT PRIMARY KEY,
    snapshot_id  TEXT NOT NULL,
    seq          INTEGER NOT NULL,
    idx          INTEGER NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN ('notice', 'report')),
    tipo         TEXT NOT NULL,
    case_id      TEXT,
    payload      TEXT NOT NULL,
    delivered_at TEXT,
    CHECK ((case_id IS NULL) = (kind = 'report')),
    CHECK (kind = 'notice' OR tipo = 'informe_de_turno'),
    UNIQUE (seq, idx)
);
CREATE UNIQUE INDEX one_alert_per_case
    ON notices (case_id) WHERE tipo = 'alerta_inmediata';
PRAGMA user_version = {SCHEMA_VERSION};
COMMIT;
"""
