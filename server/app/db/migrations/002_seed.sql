-- Seed data: the role/zone matrix, the six physical nodes, and the tuning defaults.
--
-- The matrix is the locked one from docs/DEMO_ARCHITECTURE_2026-07-19.md section 11. It
-- lives here rather than in code so an operator can change who may go where without a
-- redeploy, and so the dashboard, the policy check and the board all read one source.

INSERT INTO zones (name, label, sort_order) VALUES
  ('Reception',   'Reception',   1),
  ('Warehouse',   'Warehouse',   2),
  ('Workshop',    'Workshop',    3),
  ('Server room', 'Server room', 4);

INSERT INTO roles (name, label, default_hours_from, default_hours_to) VALUES
  ('ADMIN',   'Admin',   '00:00', '23:59'),
  ('GUARD',   'Guard',   '00:00', '23:59'),
  ('WORKER',  'Worker',  '00:00', '23:59'),
  ('IT',      'IT',      '00:00', '23:59'),
  ('VISITOR', 'Visitor', '00:00', '23:59'),
  -- The one role with a real window. It exists to demonstrate that the system checks WHEN,
  -- not only WHO: the same person is admitted at 18:30 and refused at 14:00.
  ('CLEANER', 'Cleaner', '18:00', '20:00');

-- Admin and Cleaner: everywhere. Cleaner is restricted by time, not by place.
INSERT INTO role_zone_defaults (role_id, zone_id)
  SELECT r.id, z.id FROM roles r, zones z WHERE r.name IN ('ADMIN','CLEANER');

-- Guard and Worker: everywhere except the server room. This is the wall the demo's hero
-- walks into, and the contrast that makes the role model visible on camera.
INSERT INTO role_zone_defaults (role_id, zone_id)
  SELECT r.id, z.id FROM roles r, zones z
  WHERE r.name IN ('GUARD','WORKER') AND z.name IN ('Reception','Warehouse','Workshop');

-- IT: the server room, and the way in. Deliberately NOT the warehouse or workshop, so a
-- just-in-time workshop pass is a real elevation rather than a formality.
INSERT INTO role_zone_defaults (role_id, zone_id)
  SELECT r.id, z.id FROM roles r, zones z
  WHERE r.name = 'IT' AND z.name IN ('Reception','Server room');

INSERT INTO role_zone_defaults (role_id, zone_id)
  SELECT r.id, z.id FROM roles r, zones z
  WHERE r.name = 'VISITOR' AND z.name = 'Reception';

-- The six boards. They are visually identical, so the MAC is the only way to know which
-- lump of hardware is answering to which name; these are the confirmed addresses.
INSERT INTO nodes (id, label, role, zone_id, hostname, mac_address, rotation_deg, created_at) VALUES
  ('gate-in',        'ENTRY',       'gate-in',  NULL, 'gate-in.local',        '28:84:85:9F:C6:20', 0, datetime('now')),
  ('gate-out',       'EXIT',        'gate-out', NULL, 'gate-out.local',       '28:84:85:65:6E:24', 0, datetime('now'));

INSERT INTO nodes (id, label, role, zone_id, hostname, mac_address, rotation_deg, created_at)
  SELECT 'zone-reception', 'Reception', 'zone', id, 'zone-reception.local', '28:84:85:65:64:5C', 0, datetime('now') FROM zones WHERE name='Reception';
INSERT INTO nodes (id, label, role, zone_id, hostname, mac_address, rotation_deg, created_at)
  SELECT 'zone-warehouse', 'Warehouse', 'zone', id, 'zone-warehouse.local', '28:84:85:9F:C0:EC', 0, datetime('now') FROM zones WHERE name='Warehouse';
INSERT INTO nodes (id, label, role, zone_id, hostname, mac_address, rotation_deg, created_at)
  SELECT 'zone-workshop', 'Workshop', 'zone', id, 'zone-workshop.local', '28:84:85:65:6E:F0', 0, datetime('now') FROM zones WHERE name='Workshop';
INSERT INTO nodes (id, label, role, zone_id, hostname, mac_address, rotation_deg, created_at)
  SELECT 'zone-server', 'Server room', 'zone', id, 'zone-server.local', '28:84:85:9F:C7:50', 0, datetime('now') FROM zones WHERE name='Server room';

-- Tuning. These are the live values, editable from Settings; .env only seeds a fresh
-- database. Every one of them is here rather than in code because it survives a restart,
-- which is the whole point of the table.
INSERT INTO config_kv (key, value, updated_at) VALUES
  -- Cosine similarity to accept a face. SFace's own default is 0.363; 0.45 was tuned on
  -- this exact camera hardware, where own-face scores ran 0.63-0.93.
  ('sim_threshold',           '0.45',  datetime('now')),
  -- How far the best match must beat the runner-up before it is trusted. Guards against a
  -- single poor enrolment sample winning outright.
  ('sim_margin',              '0.05',  datetime('now')),
  -- Consecutive agreeing frames before an identity is committed. Recognition confidence
  -- flickers frame to frame near the threshold; this is what stops the system announcing a
  -- name it is not sure of.
  ('confirm_frames',          '3',     datetime('now')),
  -- How long a person must stay recognised in a zone before the board moves their card, so
  -- walking past a camera in transit does not flicker them through zones.
  ('dwell_ms',                '2000',  datetime('now')),
  -- A recognition older than this cannot be bound to a physical passage at the gate.
  ('gate_bind_window_s',      '3',     datetime('now')),
  -- Repeat-alert throttles, so a lingering stranger does not flood the feed.
  ('unknown_zone_throttle_s', '30',    datetime('now')),
  ('wrong_zone_throttle_s',   '60',    datetime('now')),
  ('overstay_grace_min',      '5',     datetime('now')),
  ('voice_enabled',           '1',     datetime('now')),
  ('telegram_enabled',        '1',     datetime('now'));
