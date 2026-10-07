"""Database API for the AI and dashboard teammates. Python 3.10+."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import sqlite3

CLASS_MAP = {0: 'smoke', 1: 'fire'}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def normalize_time(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('captured_at must include timezone, e.g. +07:00 or Z')
    return dt.astimezone(timezone.utc).isoformat(timespec='microseconds')


def validate_box(item, prediction=True):
    cid = item['class_id']
    if type(cid) is not int or cid not in CLASS_MAP:
        raise ValueError('class_id must be integer 0=smoke or 1=fire')
    fields = ('xc', 'yc', 'w', 'h') + (('confidence',) if prediction else ())
    out = {'class_id': cid}
    for key in fields:
        value = item[key]
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError(f'{key} must be a number')
        out[key] = float(value)
        if not math.isfinite(out[key]):
            raise ValueError(f'{key} must be finite')
    x, y, w, h = (out[k] for k in ('xc', 'yc', 'w', 'h'))
    if not (w > 0 and h > 0 and x-w/2 >= -1e-6 and y-h/2 >= -1e-6
            and x+w/2 <= 1+1e-6 and y+h/2 <= 1+1e-6):
        raise ValueError('normalized box must lie inside the image')
    if prediction and not 0 <= out['confidence'] <= 1:
        raise ValueError('confidence must be between 0 and 1')
    return out


class FireEyesDB:
    def __init__(self, path='data/fireeyes.db'):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        return con

    def initialize(self):
        with closing(self.connect()) as con:
            version = con.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError(f'Unsupported schema version: {version}')
            con.execute('PRAGMA journal_mode=WAL')
            con.executescript(Path(__file__).with_name('schema.sql').read_text('utf-8'))

    def seed_demo(self):
        """Repeatable seed. No real cameras, model weights, or contacts required."""
        with closing(self.connect()) as con, con:
            con.execute("INSERT OR IGNORE INTO locations(name,address) VALUES (?,?)",
                        ('VKU Demo', 'Phong demo - du lieu gia lap'))
            loc = con.execute('SELECT id FROM locations WHERE name=?', ('VKU Demo',)).fetchone()[0]
            con.execute('INSERT OR IGNORE INTO cameras(location_id,name,source_ref) VALUES (?,?,?)',
                        (loc, 'Camera demo', 'demo://synthetic'))
            con.execute('INSERT OR IGNORE INTO contacts(location_id,name,destination,channel) VALUES (?,?,?,?)',
                        (loc, 'Nguoi nhan demo', 'console-only', 'console'))
            mapping = json.dumps(CLASS_MAP, sort_keys=True)
            con.execute('''INSERT OR IGNORE INTO dataset_versions
                (name,version,source_url,license_name,class_map,status) VALUES (?,?,?,?,?,?)''',
                ('D-Fire', 'planned-local-v1', 'https://github.com/gaia-solutions-on-demand/DFireDataset',
                 'CC0-1.0 as declared by source', mapping, 'planned'))
            con.execute('''INSERT OR IGNORE INTO model_versions(name,class_map,is_demo)
                VALUES (?,?,1)''', ('DEMO-NO-AI', mapping))
            return {
                'camera_id': con.execute('SELECT id FROM cameras WHERE location_id=? AND name=?',
                                         (loc, 'Camera demo')).fetchone()[0],
                'model_id': con.execute('SELECT id FROM model_versions WHERE name=?',
                                        ('DEMO-NO-AI',)).fetchone()[0],
                'contact_id': con.execute('SELECT id FROM contacts WHERE location_id=? AND destination=?',
                                          (loc, 'console-only')).fetchone()[0],
            }

    def record_frame(self, camera_id, model_id, request_id, captured_at, detections, snapshot_path=None):
        """Atomic frame + boxes. Retrying the same request is safe; changed payload is rejected."""
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError('request_id is required')
        timestamp = normalize_time(captured_at)
        boxes = [validate_box(box) for box in detections]
        payload = [model_id, timestamp, snapshot_path, boxes]
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with closing(self.connect()) as con, con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT id,payload_sha256 FROM frames WHERE camera_id=? AND request_id=?',
                              (camera_id, request_id)).fetchone()
            if old:
                if old['payload_sha256'] != digest:
                    raise ValueError('request_id already used with different payload')
                return old['id']
            model = con.execute('SELECT class_map FROM model_versions WHERE id=?', (model_id,)).fetchone()
            if model is None or json.loads(model[0]) != {'0': 'smoke', '1': 'fire'}:
                raise ValueError('model missing or class map does not match FireEyes')
            cur = con.execute('''INSERT INTO frames
                (camera_id,model_id,request_id,payload_sha256,captured_at,snapshot_path)
                VALUES (?,?,?,?,?,?)''', (camera_id,model_id,request_id,digest,timestamp,snapshot_path))
            frame_id = cur.lastrowid
            con.executemany('''INSERT INTO detections(frame_id,class_id,confidence,xc,yc,w,h)
                VALUES (?,?,?,?,?,?,?)''',
                [(frame_id, b['class_id'], b['confidence'], b['xc'], b['yc'], b['w'], b['h']) for b in boxes])
            return frame_id

    def open_incident(self, detection_id, rule_description):
        """Caller supplies an already evaluated rule. Phase 1 does not decide a fire automatically."""
        if not rule_description.strip():
            raise ValueError('rule_description is required')
        with closing(self.connect()) as con, con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('''SELECT f.camera_id,f.captured_at FROM detections d
                JOIN frames f ON f.id=d.frame_id WHERE d.id=?''', (detection_id,)).fetchone()
            if row is None:
                raise ValueError('detection does not exist')
            old = con.execute("SELECT id FROM incidents WHERE camera_id=? AND status='open'",
                              (row['camera_id'],)).fetchone()
            if old:
                return old['id']
            return con.execute('''INSERT INTO incidents
                (camera_id,trigger_detection_id,started_at,rule_description) VALUES (?,?,?,?)''',
                (row['camera_id'], detection_id, row['captured_at'], rule_description)).lastrowid

    def simulate_notification(self, incident_id, contact_id):
        """Log a simulation only. No SMS, call, email, or network operation."""
        with closing(self.connect()) as con, con:
            row = con.execute('''SELECT c.channel,c.destination FROM contacts c
                JOIN cameras cam ON cam.location_id=c.location_id
                JOIN incidents i ON i.camera_id=cam.id
                WHERE i.id=? AND c.id=?''', (incident_id,contact_id)).fetchone()
            if row is None:
                raise ValueError('recipient must belong to the incident location')
            con.execute('''INSERT OR IGNORE INTO notifications
                (incident_id,contact_id,channel,destination,status,attempted_at)
                VALUES (?,?,?,?,'simulated',?)''',
                (incident_id, contact_id, row['channel'], row['destination'], utc_now()))
            return con.execute('SELECT id FROM notifications WHERE incident_id=? AND contact_id=?',
                               (incident_id, contact_id)).fetchone()[0]

    def close_incident(self, incident_id, status, note):
        if status not in ('resolved', 'false_alarm') or not note.strip():
            raise ValueError('choose resolved/false_alarm and provide a note')
        with closing(self.connect()) as con, con:
            changed = con.execute('''UPDATE incidents SET status=?,closed_at=?,resolution_note=?
                WHERE id=? AND status='open' ''', (status,utc_now(),note,incident_id)).rowcount
            if not changed:
                raise ValueError('incident is missing or already closed')

    def list_incidents(self):
        with closing(self.connect()) as con:
            return [dict(r) for r in con.execute('''SELECT i.id,c.name AS camera,l.name AS location,
                i.status,i.started_at,i.closed_at,i.rule_description,i.resolution_note
                FROM incidents i JOIN cameras c ON c.id=i.camera_id
                JOIN locations l ON l.id=c.location_id ORDER BY i.started_at DESC''')]

    def frame_detections(self, frame_id):
        with closing(self.connect()) as con:
            return [dict(r) for r in con.execute('SELECT * FROM detections WHERE frame_id=? ORDER BY id',
                                                (frame_id,))]

    def counts(self):
        tables = ('locations','cameras','contacts','dataset_versions','dataset_samples',
                  'annotations','model_versions','frames','detections','incidents','notifications')
        with closing(self.connect()) as con:
            return {t: con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in tables}
