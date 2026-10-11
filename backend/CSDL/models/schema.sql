-- FireEyes schema v2. All application timestamps are UTC ISO 8601.
PRAGMA foreign_keys = ON;
BEGIN;
CREATE TABLE IF NOT EXISTS locations (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, address TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cameras (
 id INTEGER PRIMARY KEY, location_id INTEGER NOT NULL REFERENCES locations(id),
 name TEXT NOT NULL, source_ref TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 last_seen_at TEXT,
 UNIQUE(location_id, name)
);
-- source_ref is a video path or environment-variable name, not an RTSP password.
CREATE TABLE IF NOT EXISTS contacts (
 id INTEGER PRIMARY KEY, location_id INTEGER NOT NULL REFERENCES locations(id),
 name TEXT NOT NULL, destination TEXT NOT NULL,
 channel TEXT NOT NULL CHECK(channel IN ('sms','call','email','console')),
 UNIQUE(location_id, destination, channel)
);
CREATE TABLE IF NOT EXISTS dataset_versions (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, version TEXT NOT NULL,
 source_url TEXT NOT NULL, license_name TEXT NOT NULL,
 class_map TEXT NOT NULL, manifest_sha256 TEXT,
 status TEXT NOT NULL CHECK(status IN ('planned','verified')),
 UNIQUE(name, version)
);
CREATE TABLE IF NOT EXISTS dataset_samples (
 id INTEGER PRIMARY KEY, dataset_id INTEGER NOT NULL REFERENCES dataset_versions(id),
 image_path TEXT NOT NULL, label_path TEXT NOT NULL,
 sha256 TEXT NOT NULL CHECK(length(sha256)=64),
 split TEXT NOT NULL CHECK(split IN ('train','val','test')),
 source_group TEXT NOT NULL,
 UNIQUE(dataset_id, image_path), UNIQUE(dataset_id, sha256)
);
-- Labels for training; 0=smoke, 1=fire is the FireEyes canonical mapping.
CREATE TABLE IF NOT EXISTS annotations (
 id INTEGER PRIMARY KEY, sample_id INTEGER NOT NULL REFERENCES dataset_samples(id),
 class_id INTEGER NOT NULL CHECK(class_id IN (0,1)),
 xc REAL NOT NULL, yc REAL NOT NULL, w REAL NOT NULL, h REAL NOT NULL,
 CHECK(w>0 AND h>0 AND xc-w/2>=-0.000001 AND yc-h/2>=-0.000001
   AND xc+w/2<=1.000001 AND yc+h/2<=1.000001)
);
CREATE TRIGGER IF NOT EXISTS sample_group_insert BEFORE INSERT ON dataset_samples
WHEN EXISTS(SELECT 1 FROM dataset_samples WHERE dataset_id=NEW.dataset_id
 AND source_group=NEW.source_group AND split<>NEW.split)
BEGIN SELECT RAISE(ABORT, 'source group cannot cross dataset splits'); END;
CREATE TRIGGER IF NOT EXISTS sample_group_update BEFORE UPDATE ON dataset_samples
WHEN EXISTS(SELECT 1 FROM dataset_samples WHERE dataset_id=NEW.dataset_id
 AND source_group=NEW.source_group AND split<>NEW.split AND id<>NEW.id)
BEGIN SELECT RAISE(ABORT, 'source group cannot cross dataset splits'); END;
CREATE TABLE IF NOT EXISTS model_versions (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
 dataset_id INTEGER REFERENCES dataset_versions(id),
 weights_path TEXT, weights_sha256 TEXT,
 class_map TEXT NOT NULL,
 is_demo INTEGER NOT NULL CHECK(is_demo IN (0,1)),
 CHECK(is_demo=1 OR (dataset_id IS NOT NULL AND weights_path IS NOT NULL
   AND weights_sha256 IS NOT NULL AND length(weights_sha256)=64))
);
CREATE TABLE IF NOT EXISTS frames (
 id INTEGER PRIMARY KEY, camera_id INTEGER NOT NULL REFERENCES cameras(id),
 model_id INTEGER NOT NULL REFERENCES model_versions(id),
 request_id TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
 captured_at TEXT NOT NULL, snapshot_path TEXT,
 UNIQUE(camera_id, request_id)
);
CREATE INDEX IF NOT EXISTS idx_frames_camera_time ON frames(camera_id, captured_at);
CREATE TABLE IF NOT EXISTS detections (
 id INTEGER PRIMARY KEY, frame_id INTEGER NOT NULL REFERENCES frames(id),
 class_id INTEGER NOT NULL CHECK(class_id IN (0,1)),
 confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
 xc REAL NOT NULL, yc REAL NOT NULL, w REAL NOT NULL, h REAL NOT NULL,
 CHECK(w>0 AND h>0 AND xc-w/2>=-0.000001 AND yc-h/2>=-0.000001
   AND xc+w/2<=1.000001 AND yc+h/2<=1.000001)
);
CREATE INDEX IF NOT EXISTS idx_detections_frame ON detections(frame_id);
CREATE TABLE IF NOT EXISTS incidents (
 id INTEGER PRIMARY KEY, camera_id INTEGER NOT NULL REFERENCES cameras(id),
 trigger_detection_id INTEGER NOT NULL REFERENCES detections(id),
 started_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved','false_alarm')),
 rule_description TEXT NOT NULL,
 closed_at TEXT, resolution_note TEXT,
 acknowledged_at TEXT, acknowledged_by TEXT,
 CHECK((status='open' AND closed_at IS NULL)
   OR (status<>'open' AND closed_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_open_incident ON incidents(camera_id) WHERE status='open';
CREATE TRIGGER IF NOT EXISTS incident_camera_insert BEFORE INSERT ON incidents
WHEN NOT EXISTS(SELECT 1 FROM detections d JOIN frames f ON f.id=d.frame_id
 WHERE d.id=NEW.trigger_detection_id AND f.camera_id=NEW.camera_id)
BEGIN SELECT RAISE(ABORT, 'incident evidence must come from the same camera'); END;
CREATE TRIGGER IF NOT EXISTS incident_camera_update BEFORE UPDATE OF camera_id,trigger_detection_id ON incidents
WHEN NOT EXISTS(SELECT 1 FROM detections d JOIN frames f ON f.id=d.frame_id
 WHERE d.id=NEW.trigger_detection_id AND f.camera_id=NEW.camera_id)
BEGIN SELECT RAISE(ABORT, 'incident evidence must come from the same camera'); END;
CREATE INDEX IF NOT EXISTS idx_incident_status_time ON incidents(status, started_at);
CREATE TABLE IF NOT EXISTS notifications (
 id INTEGER PRIMARY KEY, incident_id INTEGER NOT NULL REFERENCES incidents(id),
 contact_id INTEGER NOT NULL REFERENCES contacts(id),
 channel TEXT NOT NULL, destination TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','sent','failed','simulated')),
 attempted_at TEXT NOT NULL, provider_message_id TEXT, error_message TEXT,
 UNIQUE(incident_id, contact_id)
);
PRAGMA user_version = 2;
COMMIT;
