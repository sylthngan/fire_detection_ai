from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from backend.CSDL.models.database import FireEyesDB


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = FireEyesDB(Path(self.tmp.name) / 'test.db')
        self.db.initialize()
        self.ids = self.db.seed_demo()
        self.box = dict(class_id=0, confidence=0.9, xc=0.5, yc=0.5, w=0.2, h=0.2)

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, request='f1', boxes=None, camera=None, time='2026-09-30T01:00:00+07:00'):
        return self.db.record_frame(camera or self.ids['camera_id'], self.ids['model_id'],
                                    request, time, [self.box] if boxes is None else boxes)

    def test_persistence_and_repeatable_seed(self):
        self.record()
        db = FireEyesDB(self.db.path)
        db.initialize()
        self.assertEqual(self.ids, db.seed_demo())
        self.assertEqual(db.counts()['frames'], 1)
        self.assertEqual(db.counts()['cameras'], 1)

    def test_migrates_schema_v1_status_and_acknowledgement_columns(self):
        with closing(self.db.connect()) as con, con:
            con.execute('ALTER TABLE cameras DROP COLUMN last_seen_at')
            con.execute('ALTER TABLE incidents DROP COLUMN acknowledged_at')
            con.execute('ALTER TABLE incidents DROP COLUMN acknowledged_by')
            con.execute('PRAGMA user_version = 1')

        self.db.initialize()

        with closing(self.db.connect()) as con:
            camera_columns = {
                row['name'] for row in con.execute('PRAGMA table_info(cameras)')
            }
            incident_columns = {
                row['name'] for row in con.execute('PRAGMA table_info(incidents)')
            }
            self.assertIn('last_seen_at', camera_columns)
            self.assertIn('acknowledged_at', incident_columns)
            self.assertIn('acknowledged_by', incident_columns)
            self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0], 2)

    def test_duplicate_request_and_conflicting_retry(self):
        self.assertEqual(self.record(), self.record())
        with self.assertRaises(ValueError):
            self.record(boxes=[dict(self.box, confidence=0.8)])
        self.assertEqual(self.db.counts()['frames'], 1)
        self.assertEqual(self.db.counts()['detections'], 1)

    def test_atomic_validation_and_foreign_key(self):
        with self.assertRaises(ValueError):
            self.record(boxes=[self.box, dict(self.box, confidence=1.5)])
        with self.assertRaises(sqlite3.IntegrityError):
            self.record(camera=999)
        self.assertEqual(self.db.counts()['frames'], 0)
        self.assertEqual(self.db.counts()['detections'], 0)

    def test_invalid_labels_boxes_and_nan(self):
        for update in ({'class_id':2}, {'class_id':True}, {'xc':0.99}, {'w':-1},
                       {'confidence':float('nan')}, {'yc':float('inf')}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.record(boxes=[dict(self.box, **update)])

    def test_negative_frame_and_timezone(self):
        fid = self.record(boxes=[])
        self.assertEqual(self.db.frame_detections(fid), [])
        with closing(self.db.connect()) as con:
            stamp = con.execute('SELECT captured_at FROM frames WHERE id=?', (fid,)).fetchone()[0]
        self.assertEqual(stamp, '2026-09-29T18:00:00.000000+00:00')
        with self.assertRaises(ValueError):
            self.record(request='bad-time', time='2026-09-30T01:00:00')

    def test_incident_dedup_close_and_new_event(self):
        fid = self.record()
        did = self.db.frame_detections(fid)[0]['id']
        iid = self.db.open_incident(did, 'test rule')
        self.assertEqual(iid, self.db.open_incident(did, 'same event'))
        self.db.close_incident(iid, 'false_alarm', 'Steam, manually reviewed')
        with self.assertRaises(ValueError):
            self.db.close_incident(iid, 'resolved', 'Already closed')
        fid2 = self.record('f2')
        new = self.db.open_incident(self.db.frame_detections(fid2)[0]['id'], 'new event')
        self.assertNotEqual(iid, new)

    def test_notification_simulated_deduplicated_and_location_checked(self):
        fid = self.record()
        iid = self.db.open_incident(self.db.frame_detections(fid)[0]['id'], 'test')
        n1 = self.db.simulate_notification(iid, self.ids['contact_id'])
        self.assertEqual(n1, self.db.simulate_notification(iid, self.ids['contact_id']))
        with closing(self.db.connect()) as con, con:
            loc = con.execute("INSERT INTO locations(name,address) VALUES ('Other','Other')").lastrowid
            other = con.execute('INSERT INTO contacts(location_id,name,destination,channel) VALUES (?,?,?,?)',
                                (loc,'Other','other','console')).lastrowid
            self.assertEqual(con.execute('SELECT status FROM notifications WHERE id=?', (n1,)).fetchone()[0],
                             'simulated')
        with self.assertRaises(ValueError):
            self.db.simulate_notification(iid, other)

    def test_dataset_duplicates_and_group_leakage_rejected(self):
        with closing(self.db.connect()) as con, con:
            dataset = con.execute('SELECT id FROM dataset_versions').fetchone()[0]
            sql = '''INSERT INTO dataset_samples
                (dataset_id,image_path,label_path,sha256,split,source_group) VALUES (?,?,?,?,?,?)'''
            con.execute(sql, (dataset,'a.jpg','a.txt','a'*64,'train','video-A'))
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(sql, (dataset,'b.jpg','b.txt','b'*64,'test','video-A'))
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(sql, (dataset,'c.jpg','c.txt','a'*64,'test','video-C'))


if __name__ == '__main__':
    unittest.main()
