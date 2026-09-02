-- Charon v2 initial schema.
--
-- One file per real change from here on, never edited after it has been applied: the
-- migration list is part of the iteration evidence, and an edited migration silently
-- diverges from every database that already ran it.
--
-- Design rules this schema follows:
--   * Roles, zones and the role->zone matrix are DATA, not a Python dict. Adding a zone is
--     a row, not an edit in three files. The old build hardcoded the zone list in the
--     server, in admin.html and in board.html, and they could disagree.
--   * Anything that changes how strict the system is has to survive a restart, so mode
--     flags live in config_kv rather than in memory.
--   * Face data is stored as embeddings only, never images.

PRAGMA foreign_keys = ON;

CREATE TABLE schema_migrations (
  version     INTEGER PRIMARY KEY,
  applied_at  TEXT NOT NULL
);

-- ---------------------------------------------------------------- roles and zones

CREATE TABLE roles (
  id                  INTEGER PRIMARY KEY,
  name                TEXT NOT NULL UNIQUE,        -- GUARD, IT, ...
  label               TEXT NOT NULL,               -- shown in the UI
  -- A role may carry a default access window (the Cleaner is only allowed on site
  -- 18:00-20:00). These seed a person's own hours; the person's values stay authoritative,
  -- so one individual can be varied without inventing a new role.
  default_hours_from  TEXT NOT NULL DEFAULT '00:00',
  default_hours_to    TEXT NOT NULL DEFAULT '23:59'
);

CREATE TABLE zones (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  label       TEXT NOT NULL,
  sort_order  INTEGER NOT NULL DEFAULT 0           -- column order on the board
);

CREATE TABLE role_zone_defaults (
  role_id  INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  zone_id  INTEGER NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  PRIMARY KEY (role_id, zone_id)
);

-- ---------------------------------------------------------------- people

CREATE TABLE people (
  id                INTEGER PRIMARY KEY,
  name              TEXT NOT NULL UNIQUE,
  role_id           INTEGER NOT NULL REFERENCES roles(id),
  telegram_chat_id  TEXT NOT NULL DEFAULT '',
  -- Access window, "HH:MM". A window where from > to crosses midnight and is handled as
  -- such; the old build compared these lexically and silently refused every night shift,
  -- while its overstay sweep did handle midnight - two halves of one system disagreeing.
  hours_from        TEXT NOT NULL DEFAULT '00:00',
  hours_to          TEXT NOT NULL DEFAULT '23:59',
  valid_until       TEXT NOT NULL DEFAULT '',      -- date, '' = no expiry
  access_until      TEXT NOT NULL DEFAULT '',      -- timestamp; temporary out-of-hours extension
  max_hours         REAL,                          -- NULL = no on-site cap
  status            TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended')),
  is_dispatcher     INTEGER NOT NULL DEFAULT 0,    -- receives security alerts
  -- System-managed. Never writable through the person-edit endpoint.
  presence          TEXT NOT NULL DEFAULT 'out' CHECK (presence IN ('in','out')),
  session_token     TEXT NOT NULL DEFAULT '',
  entry_time        TEXT NOT NULL DEFAULT '',
  -- NULL while on site but not yet seen by any zone camera. Entry deliberately does NOT
  -- place anyone in Reception: the Reception camera does that, which is what makes the
  -- first zone transition real rather than assumed.
  at_zone_id        INTEGER REFERENCES zones(id) ON DELETE SET NULL,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);

CREATE INDEX idx_people_presence ON people(presence);

-- Rows here REPLACE the role default entirely, in both directions. The old build let an
-- override widen access but never narrow it for an ADMIN, because the "all zones" role was
-- short-circuited before the override was consulted - an authorisation gap found in review.
CREATE TABLE person_zone_overrides (
  person_id  INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
  zone_id    INTEGER NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  PRIMARY KEY (person_id, zone_id)
);

-- Just-in-time grants: each zone carries its OWN expiry so one pass lapsing does not
-- disturb another, and nothing has to be manually reverted.
CREATE TABLE zone_grants (
  id          INTEGER PRIMARY KEY,
  person_id   INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
  zone_id     INTEGER NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  expires_at  TEXT NOT NULL,
  granted_by  TEXT NOT NULL DEFAULT 'admin',
  granted_at  TEXT NOT NULL,
  revoked_at  TEXT
);

-- At most one live grant per person per zone; expired and revoked rows are kept as history.
CREATE UNIQUE INDEX idx_zone_grants_live
  ON zone_grants(person_id, zone_id) WHERE revoked_at IS NULL;

-- ---------------------------------------------------------------- biometrics

CREATE TABLE face_embeddings (
  id             INTEGER PRIMARY KEY,
  person_id      INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
  vec            BLOB NOT NULL,                    -- float32, L2-normalised, ndarray.tobytes()
  dim            INTEGER NOT NULL,
  -- Embeddings from different recognisers are not comparable. Stamping the model means a
  -- change of recogniser cannot silently start matching old vectors against new ones.
  model_version  TEXT NOT NULL,
  source         TEXT NOT NULL CHECK (source IN ('live','photo')),
  node_id        TEXT,                             -- which camera captured it, for 'live'
  created_at     TEXT NOT NULL
);

CREATE INDEX idx_face_embeddings_person ON face_embeddings(person_id);

-- ---------------------------------------------------------------- nodes

CREATE TABLE nodes (
  id                   TEXT PRIMARY KEY,           -- gate-in, zone-server, ...
  label                TEXT NOT NULL,
  role                 TEXT NOT NULL CHECK (role IN ('gate-in','gate-out','zone')),
  zone_id              INTEGER REFERENCES zones(id) ON DELETE SET NULL,
  hostname             TEXT NOT NULL,              -- <id>.local
  mac_address          TEXT NOT NULL DEFAULT '',   -- the only way to tell the boards apart
  -- Per node, because six cameras are mounted six different ways. The old build applied one
  -- global 180 degree rotation inherited from when there was a single camera.
  rotation_deg         INTEGER NOT NULL DEFAULT 0 CHECK (rotation_deg IN (0,90,180,270)),
  -- Readable cache of the thresholds. The board's NVS copy is authoritative; this exists so
  -- the UI can show them without waking anything.
  wake_cm              INTEGER,
  pass_cm              INTEGER,
  thresholds_synced_at TEXT,
  enabled              INTEGER NOT NULL DEFAULT 1,
  created_at           TEXT NOT NULL
);

-- ---------------------------------------------------------------- audit

-- Structured, not a text file. "SELECT ts, message ORDER BY ts" still reproduces the old
-- flat log for the report, but severity and the foreign keys make it queryable.
CREATE TABLE audit_log (
  id            INTEGER PRIMARY KEY,
  ts            TEXT NOT NULL,
  actor         TEXT NOT NULL DEFAULT 'system',
  event_type    TEXT NOT NULL,
  severity      TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info','warn','alert')),
  node_id       TEXT REFERENCES nodes(id) ON DELETE SET NULL,
  person_id     INTEGER REFERENCES people(id) ON DELETE SET NULL,
  zone_id       INTEGER REFERENCES zones(id) ON DELETE SET NULL,
  message       TEXT NOT NULL,                     -- human-readable, for the report
  details_json  TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_audit_ts       ON audit_log(ts);
CREATE INDEX idx_audit_severity ON audit_log(severity, ts);

-- ---------------------------------------------------------------- persistent config

-- Mode flags live here, not in memory. An in-memory strictness flag reverts silently on
-- every restart and nothing on screen says it happened.
CREATE TABLE config_kv (
  key         TEXT PRIMARY KEY,
  value       TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
