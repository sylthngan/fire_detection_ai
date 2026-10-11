"""Database API for the AI and dashboard teammates. Python 3.10+."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import sqlite3

CLASS_MAP = {0: 'smoke', 1: 'fire'}
D_FIRE_CLASS_MAP = {0: 'fire', 1: 'smoke'}


class IdempotencyConflictError(ValueError):
    """A request ID was reused with a different frame payload."""


class ModelReferenceError(ValueError):
    """The requested model is missing or uses an incompatible class map."""


class CameraUnavailableError(ValueError):
    """A camera is disabled and cannot send new frames."""


class RecordNotFoundError(ValueError):
    """A requested database record does not exist."""


class IncidentAlreadyClosedError(ValueError):
    """An open incident was required, but it has already been closed."""


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
            if version not in (0, 1, 2):
                raise RuntimeError(f'Unsupported schema version: {version}')
            con.execute('PRAGMA journal_mode=WAL')
            con.executescript(Path(__file__).with_name('schema.sql').read_text('utf-8'))
            if version == 1:
                camera_columns = {
                    row['name'] for row in con.execute('PRAGMA table_info(cameras)')
                }
                incident_columns = {
                    row['name'] for row in con.execute('PRAGMA table_info(incidents)')
                }
                if 'last_seen_at' not in camera_columns:
                    con.execute('ALTER TABLE cameras ADD COLUMN last_seen_at TEXT')
                if 'acknowledged_at' not in incident_columns:
                    con.execute('ALTER TABLE incidents ADD COLUMN acknowledged_at TEXT')
                if 'acknowledged_by' not in incident_columns:
                    con.execute('ALTER TABLE incidents ADD COLUMN acknowledged_by TEXT')
                con.execute('PRAGMA user_version = 2')

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
            dataset_mapping = json.dumps(D_FIRE_CLASS_MAP, sort_keys=True)
            con.execute('''INSERT OR IGNORE INTO dataset_versions
                (name,version,source_url,license_name,class_map,status) VALUES (?,?,?,?,?,?)''',
                ('D-Fire', 'planned-local-v1', 'https://github.com/gaia-solutions-on-demand/DFireDataset',
                 'CC0-1.0 as declared by source', dataset_mapping, 'planned'))
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

    def create_location(self, name, address):
        with closing(self.connect()) as con, con:
            cursor = con.execute(
                'INSERT INTO locations(name,address) VALUES (?,?)',
                (name, address),
            )
            return cursor.lastrowid

    def create_camera(self, location_id, name, source_ref):
        with closing(self.connect()) as con, con:
            cursor = con.execute(
                'INSERT INTO cameras(location_id,name,source_ref) VALUES (?,?,?)',
                (location_id, name, source_ref),
            )
            return cursor.lastrowid

    def create_dataset(
        self,
        name,
        version,
        source_url,
        license_name,
        class_map,
        manifest_sha256=None,
        status='planned',
    ):
        serialized_class_map = json.dumps(class_map, sort_keys=True)
        with closing(self.connect()) as con, con:
            cursor = con.execute(
                '''INSERT INTO dataset_versions
                    (name,version,source_url,license_name,class_map,
                     manifest_sha256,status)
                    VALUES (?,?,?,?,?,?,?)''',
                (
                    name,
                    version,
                    source_url,
                    license_name,
                    serialized_class_map,
                    manifest_sha256,
                    status,
                ),
            )
            return cursor.lastrowid

    def create_model(self, name, dataset_id, weights_path, weights_sha256):
        class_map = json.dumps(CLASS_MAP, sort_keys=True)
        with closing(self.connect()) as con, con:
            cursor = con.execute(
                '''INSERT INTO model_versions
                    (name,dataset_id,weights_path,weights_sha256,class_map,is_demo)
                    VALUES (?,?,?,?,?,0)''',
                (name, dataset_id, weights_path, weights_sha256, class_map),
            )
            return cursor.lastrowid

    def list_locations(self):
        with closing(self.connect()) as con:
            return [
                dict(row)
                for row in con.execute(
                    'SELECT id,name,address FROM locations ORDER BY id'
                )
            ]

    def list_cameras(self):
        with closing(self.connect()) as con:
            return [
                dict(row)
                for row in con.execute(
                    '''SELECT c.id,c.location_id,l.name AS location,c.name,
                              c.source_ref,c.enabled,c.last_seen_at
                       FROM cameras c JOIN locations l ON l.id=c.location_id
                       ORDER BY c.id'''
                )
            ]

    def set_camera_enabled(self, camera_id, enabled):
        with closing(self.connect()) as con, con:
            changed = con.execute(
                '''UPDATE cameras SET enabled=?,
                          last_seen_at=CASE WHEN ?=1 THEN NULL ELSE last_seen_at END
                   WHERE id=?''',
                (int(enabled), int(enabled), camera_id),
            ).rowcount
            if not changed:
                raise RecordNotFoundError('camera does not exist')
        return self.get_camera_status(camera_id)

    def get_camera_status(self, camera_id, stale_after_seconds=45):
        with closing(self.connect()) as con:
            row = con.execute(
                '''SELECT id,name,enabled,last_seen_at
                   FROM cameras WHERE id=?''',
                (camera_id,),
            ).fetchone()
        if row is None:
            return None

        last_seen_at = row['last_seen_at']
        if not row['enabled']:
            status = 'stopped'
        elif last_seen_at is None:
            status = 'disconnected'
        else:
            last_seen = datetime.fromisoformat(last_seen_at)
            elapsed = (datetime.now(timezone.utc) - last_seen).total_seconds()
            status = (
                'active' if elapsed <= stale_after_seconds else 'disconnected'
            )
        return {
            'camera_id': row['id'],
            'name': row['name'],
            'status': status,
            'enabled': bool(row['enabled']),
            'last_seen_at': last_seen_at,
            'stale_after_seconds': stale_after_seconds,
        }

    def record_camera_heartbeat(self, camera_id):
        last_seen_at = utc_now()
        with closing(self.connect()) as con, con:
            con.execute('BEGIN IMMEDIATE')
            camera = con.execute(
                'SELECT enabled FROM cameras WHERE id=?',
                (camera_id,),
            ).fetchone()
            if camera is None:
                raise RecordNotFoundError('camera does not exist')
            if not camera['enabled']:
                raise CameraUnavailableError('camera is stopped')
            con.execute(
                'UPDATE cameras SET last_seen_at=? WHERE id=?',
                (last_seen_at, camera_id),
            )
        return last_seen_at

    def list_datasets(self):
        with closing(self.connect()) as con:
            return [
                dict(row)
                for row in con.execute(
                    '''SELECT id,name,version,source_url,license_name,
                              manifest_sha256,status
                       FROM dataset_versions ORDER BY id'''
                )
            ]

    def list_models(self):
        with closing(self.connect()) as con:
            return [
                dict(row)
                for row in con.execute(
                    '''SELECT id,name,dataset_id,weights_path,weights_sha256,
                              class_map,is_demo
                       FROM model_versions ORDER BY id'''
                )
            ]

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
            camera = con.execute(
                'SELECT enabled FROM cameras WHERE id=?',
                (camera_id,),
            ).fetchone()
            if camera is not None and not camera['enabled']:
                raise CameraUnavailableError('camera is stopped')
            old = con.execute('SELECT id,payload_sha256 FROM frames WHERE camera_id=? AND request_id=?',
                              (camera_id, request_id)).fetchone()
            if old:
                if old['payload_sha256'] != digest:
                    raise IdempotencyConflictError(
                        'request_id already used with different payload'
                    )
                con.execute(
                    'UPDATE cameras SET last_seen_at=? WHERE id=?',
                    (utc_now(), camera_id),
                )
                return old['id']
            model = con.execute('SELECT class_map FROM model_versions WHERE id=?', (model_id,)).fetchone()
            if model is None or json.loads(model[0]) != {'0': 'smoke', '1': 'fire'}:
                raise ModelReferenceError(
                    'model missing or class map does not match FireEyes'
                )
            cur = con.execute('''INSERT INTO frames
                (camera_id,model_id,request_id,payload_sha256,captured_at,snapshot_path)
                VALUES (?,?,?,?,?,?)''', (camera_id,model_id,request_id,digest,timestamp,snapshot_path))
            frame_id = cur.lastrowid
            con.execute(
                'UPDATE cameras SET last_seen_at=? WHERE id=?',
                (utc_now(), camera_id),
            )
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
        if status not in ('resolved', 'false_alarm'):
            raise ValueError('status must be resolved or false_alarm')
        if not note.strip():
            raise ValueError('a resolution note is required')
        with closing(self.connect()) as con, con:
            changed = con.execute('''UPDATE incidents SET status=?,closed_at=?,resolution_note=?
                WHERE id=? AND status='open' ''', (status,utc_now(),note,incident_id)).rowcount
            if not changed:
                row = con.execute(
                    'SELECT id FROM incidents WHERE id=?',
                    (incident_id,),
                ).fetchone()
                if row is None:
                    raise RecordNotFoundError('incident does not exist')
                raise IncidentAlreadyClosedError('incident is already closed')
        return self.get_incident(incident_id)

    def acknowledge_incident(self, incident_id, acknowledged_by):
        if not acknowledged_by.strip():
            raise ValueError('acknowledged_by is required')
        with closing(self.connect()) as con, con:
            con.execute(
                '''UPDATE incidents
                   SET acknowledged_at=?, acknowledged_by=?
                   WHERE id=? AND acknowledged_at IS NULL''',
                (utc_now(), acknowledged_by.strip(), incident_id),
            )
            row = con.execute(
                'SELECT id FROM incidents WHERE id=?',
                (incident_id,),
            ).fetchone()
            if row is None:
                raise RecordNotFoundError('alert does not exist')
        return self.get_incident(incident_id)

    def list_incidents(self, acknowledged=None, limit=None, offset=0):
        query = '''SELECT i.id,c.id AS camera_id,c.name AS camera,
                          l.name AS location,i.status,i.started_at,
                          i.closed_at,i.rule_description,i.resolution_note,
                          i.acknowledged_at,i.acknowledged_by,
                          CASE d.class_id WHEN 1 THEN 'fire' ELSE 'smoke' END
                              AS alert_class,
                          d.confidence,f.snapshot_path
                   FROM incidents i JOIN cameras c ON c.id=i.camera_id
                   JOIN locations l ON l.id=c.location_id
                   JOIN detections d ON d.id=i.trigger_detection_id
                   JOIN frames f ON f.id=d.frame_id'''
        parameters = []
        if acknowledged is not None:
            query += (
                ' WHERE i.acknowledged_at IS NOT NULL'
                if acknowledged
                else ' WHERE i.acknowledged_at IS NULL'
            )
        query += ' ORDER BY i.started_at DESC,i.id DESC'
        if limit is not None:
            query += ' LIMIT ? OFFSET ?'
            parameters.extend((limit, offset))
        with closing(self.connect()) as con:
            return [
                dict(row)
                for row in con.execute(query, parameters)
            ]

    def get_incident(self, incident_id):
        return next(
            (
                incident
                for incident in self.list_incidents()
                if incident['id'] == incident_id
            ),
            None,
        )

    def list_detection_history(
        self,
        camera_id=None,
        limit=100,
        offset=0,
    ):
        query = '''SELECT d.id AS detection_id,f.id AS frame_id,
                          c.id AS camera_id,c.name AS camera,
                          m.id AS model_id,m.name AS model,
                          f.request_id,f.captured_at,d.class_id,
                          CASE d.class_id WHEN 1 THEN 'fire' ELSE 'smoke' END
                              AS detection_class,
                          d.confidence,d.xc,d.yc,d.w,d.h,f.snapshot_path
                   FROM detections d
                   JOIN frames f ON f.id=d.frame_id
                   JOIN cameras c ON c.id=f.camera_id
                   JOIN model_versions m ON m.id=f.model_id'''
        parameters = []
        if camera_id is not None:
            query += ' WHERE c.id=?'
            parameters.append(camera_id)
        query += ' ORDER BY f.captured_at DESC,d.id DESC LIMIT ? OFFSET ?'
        parameters.extend((limit, offset))
        with closing(self.connect()) as con:
            return [dict(row) for row in con.execute(query, parameters)]

    def frame_detections(self, frame_id):
        with closing(self.connect()) as con:
            return [dict(r) for r in con.execute('SELECT * FROM detections WHERE frame_id=? ORDER BY id',
                                                (frame_id,))]

    def counts(self):
        tables = ('locations','cameras','contacts','dataset_versions','dataset_samples',
                  'annotations','model_versions','frames','detections','incidents','notifications')
        with closing(self.connect()) as con:
            return {t: con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in tables}
