from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.CSDL.models.database import FireEyesDB


class BackendAPITests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "fireeyes.db"
        self.snapshot_root = Path(self.temp_dir.name) / "screenshots"
        self.snapshot_root.mkdir()
        db = FireEyesDB(self.db_path)
        db.initialize()
        self.ids = db.seed_demo()
        self.client_context = TestClient(
            create_app(self.db_path, self.snapshot_root)
        )
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def payload(self):
        return {
            "camera_id": self.ids["camera_id"],
            "model_id": self.ids["model_id"],
            "request_id": "camera-1:frame-1",
            "captured_at": "2026-09-30T01:00:00+07:00",
            "detections": [
                {
                    "class_id": 1,
                    "confidence": 0.91,
                    "xc": 0.5,
                    "yc": 0.5,
                    "w": 0.2,
                    "h": 0.3,
                }
            ],
        }

    def test_health_and_stats(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        stats = self.client.get("/api/stats").json()
        self.assertEqual(stats["frames"], 0)
        self.assertEqual(stats["detections"], 0)

    def test_ingests_frame_and_detections(self):
        response = self.client.post("/api/frames", json=self.payload())

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "stored")
        stats = self.client.get("/api/stats").json()
        self.assertEqual(stats["frames"], 1)
        self.assertEqual(stats["detections"], 1)

    def test_confirmed_detection_opens_incident_for_ui(self):
        snapshot_path = self.snapshot_root / "fire.jpg"
        snapshot_path.write_bytes(b"fake-jpeg-data")
        payload = self.payload()
        payload["confirmed_classes"] = ["fire"]
        payload["snapshot_path"] = str(snapshot_path)

        response = self.client.post("/api/frames", json=payload)

        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(response.json()["incident_id"])
        incidents = self.client.get("/api/incidents").json()
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]["alert_class"], "fire")
        self.assertAlmostEqual(incidents[0]["confidence"], 0.91)
        self.assertEqual(
            self.client.get(
                f"/api/alerts/{response.json()['incident_id']}/snapshot"
            ).content,
            b"fake-jpeg-data",
        )

    def test_snapshot_endpoint_does_not_serve_files_outside_snapshot_root(self):
        outside_path = Path(self.temp_dir.name) / "secret.jpg"
        outside_path.write_bytes(b"not-for-app")
        payload = self.payload()
        payload["snapshot_path"] = str(outside_path)
        payload["confirmed_classes"] = ["fire"]
        incident_id = self.client.post(
            "/api/detections",
            json=payload,
        ).json()["incident_id"]

        response = self.client.get(
            f"/api/alerts/{incident_id}/snapshot"
        )
        self.assertEqual(response.status_code, 404)
        self.assertNotEqual(response.content, b"not-for-app")

    def test_camera_status_heartbeat_and_stopped_state(self):
        camera_id = self.ids["camera_id"]
        status_url = f"/api/cameras/{camera_id}/status"
        heartbeat_url = f"/api/cameras/{camera_id}/heartbeat"

        self.assertEqual(
            self.client.get(status_url).json()["status"],
            "disconnected",
        )
        self.assertEqual(
            self.client.post(heartbeat_url).json()["status"],
            "received",
        )
        self.assertEqual(
            self.client.get(status_url).json()["status"],
            "active",
        )
        self.assertEqual(
            self.client.patch(status_url, json={"enabled": False}).json()[
                "status"
            ],
            "stopped",
        )
        self.assertEqual(self.client.post(heartbeat_url).status_code, 409)
        self.assertEqual(
            self.client.post("/api/frames", json=self.payload()).status_code,
            409,
        )
        self.assertEqual(
            self.client.patch(status_url, json={"enabled": True}).json()[
                "status"
            ],
            "disconnected",
        )
        self.assertEqual(self.client.post(heartbeat_url).status_code, 200)
        self.assertEqual(
            self.client.get(status_url).json()["status"],
            "active",
        )

    def test_detection_history_and_alert_acknowledgement(self):
        payload = self.payload()
        payload["confirmed_classes"] = ["fire"]
        self.assertEqual(
            self.client.post("/api/detections", json=payload).status_code,
            201,
        )

        history = self.client.get("/api/detections/history?limit=1").json()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["detection_class"], "fire")
        self.assertEqual(history[0]["camera_id"], self.ids["camera_id"])
        self.assertEqual(
            self.client.get("/api/detections/history?limit=0").status_code,
            422,
        )

        alerts = self.client.get("/api/alerts").json()
        self.assertEqual(len(alerts), 1)
        alert_id = alerts[0]["id"]
        self.assertEqual(self.client.get("/api/alerts/latest").json()["id"], alert_id)
        self.assertIsNone(alerts[0]["acknowledged_at"])

        acknowledge_url = f"/api/alerts/{alert_id}/acknowledge"
        first = self.client.patch(
            acknowledge_url,
            json={"acknowledged_by": "Operator 1"},
        ).json()
        acknowledged_at = first["acknowledged_at"]
        second = self.client.patch(
            acknowledge_url,
            json={"acknowledged_by": "Operator 2"},
        ).json()
        self.assertEqual(second["acknowledged_at"], acknowledged_at)
        self.assertEqual(second["acknowledged_by"], "Operator 1")
        self.assertEqual(
            self.client.get("/api/alerts?acknowledged=true").json()[0]["id"],
            alert_id,
        )
        self.assertEqual(
            self.client.get("/api/alerts?acknowledged=false").json(),
            [],
        )
        self.assertEqual(
            self.client.patch(
                "/api/alerts/999/acknowledge",
                json={"acknowledged_by": "Operator"},
            ).status_code,
            404,
        )

    def test_resolves_alert_or_marks_false_alarm(self):
        payload = self.payload()
        payload["confirmed_classes"] = ["fire"]
        created = self.client.post("/api/detections", json=payload)
        alert_id = created.json()["incident_id"]
        resolve_url = f"/api/alerts/{alert_id}/resolve"

        resolved = self.client.patch(
            resolve_url,
            json={"status": "resolved", "note": "Fire was extinguished"},
        )
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(resolved.json()["status"], "resolved")
        self.assertEqual(resolved.json()["resolution_note"], "Fire was extinguished")
        self.assertIsNotNone(resolved.json()["closed_at"])
        self.assertEqual(
            self.client.patch(
                resolve_url,
                json={"status": "false_alarm", "note": "Duplicate report"},
            ).status_code,
            409,
        )

        second_payload = self.payload()
        second_payload["request_id"] = "camera-1:frame-2"
        second_payload["confirmed_classes"] = ["fire"]
        second_payload["captured_at"] = "2026-09-30T01:01:00+07:00"
        second_id = self.client.post(
            "/api/detections",
            json=second_payload,
        ).json()["incident_id"]
        false_alarm = self.client.patch(
            f"/api/alerts/{second_id}/resolve",
            json={"status": "false_alarm", "note": "Smoke was steam"},
        )
        self.assertEqual(false_alarm.status_code, 200)
        self.assertEqual(false_alarm.json()["status"], "false_alarm")

        self.assertEqual(
            self.client.patch(
                "/api/alerts/999/resolve",
                json={"status": "resolved", "note": "Not found"},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/alerts/{second_id}/resolve",
                json={"status": "open", "note": "Invalid status"},
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/alerts/{second_id}/resolve",
                json={"status": "resolved", "note": "   "},
            ).status_code,
            422,
        )

    def test_confirmed_class_requires_matching_detection(self):
        payload = self.payload()
        payload["detections"] = []
        payload["confirmed_classes"] = ["fire"]

        response = self.client.post("/api/frames", json=payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/api/stats").json()["frames"], 0)

    def test_identical_retry_is_idempotent(self):
        first = self.client.post("/api/frames", json=self.payload())
        second = self.client.post("/api/frames", json=self.payload())

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["frame_id"], second.json()["frame_id"])
        self.assertEqual(self.client.get("/api/stats").json()["frames"], 1)

    def test_conflicting_retry_returns_conflict(self):
        self.client.post("/api/frames", json=self.payload())
        changed_payload = self.payload()
        changed_payload["detections"][0]["confidence"] = 0.7

        response = self.client.post("/api/frames", json=changed_payload)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get("/api/stats").json()["frames"], 1)

    def test_rejects_invalid_box_and_unknown_references(self):
        invalid_box = self.payload()
        invalid_box["detections"][0]["class_id"] = 2
        self.assertEqual(
            self.client.post("/api/frames", json=invalid_box).status_code,
            422,
        )

        unknown_camera = self.payload()
        unknown_camera["camera_id"] = 999
        self.assertEqual(
            self.client.post("/api/frames", json=unknown_camera).status_code,
            409,
        )

        unknown_model = self.payload()
        unknown_model["model_id"] = 999
        self.assertEqual(
            self.client.post("/api/frames", json=unknown_model).status_code,
            409,
        )
        self.assertEqual(self.client.get("/api/stats").json()["frames"], 0)

    def test_rejects_timestamp_without_timezone(self):
        payload = self.payload()
        payload["captured_at"] = "2026-09-30T01:00:00"

        response = self.client.post("/api/frames", json=payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/api/stats").json()["frames"], 0)

    def test_registers_real_records_then_accepts_frame(self):
        location_response = self.client.post(
            "/api/locations",
            json={"name": "Lab", "address": "Building A"},
        )
        self.assertEqual(location_response.status_code, 201)
        location_id = location_response.json()["id"]

        camera_response = self.client.post(
            "/api/cameras",
            json={
                "location_id": location_id,
                "name": "Camera 1",
                "source_ref": "camera-index:0",
            },
        )
        self.assertEqual(camera_response.status_code, 201)
        camera_id = camera_response.json()["id"]

        dataset_response = self.client.post(
            "/api/datasets",
            json={
                "name": "D-Fire",
                "version": "local-v1",
                "source_url": "https://example.com/d-fire",
                "license_name": "See source terms",
                "class_map": {"0": "fire", "1": "smoke"},
            },
        )
        self.assertEqual(dataset_response.status_code, 201)
        dataset_id = dataset_response.json()["id"]

        model_response = self.client.post(
            "/api/models",
            json={
                "name": "fire-model-v1",
                "dataset_id": dataset_id,
                "weights_path": "runs/detect/fire_ai/weights/best.pt",
                "weights_sha256": "a" * 64,
            },
        )
        self.assertEqual(model_response.status_code, 201)
        model_id = model_response.json()["id"]

        payload = self.payload()
        payload["camera_id"] = camera_id
        payload["model_id"] = model_id
        response = self.client.post("/api/frames", json=payload)

        self.assertEqual(response.status_code, 201)
        self.assertIn(
            camera_id,
            [camera["id"] for camera in self.client.get("/api/cameras").json()],
        )
        self.assertIn(
            model_id,
            [model["id"] for model in self.client.get("/api/models").json()],
        )
        self.assertIn(
            dataset_id,
            [dataset["id"] for dataset in self.client.get("/api/datasets").json()],
        )
        self.assertEqual(self.client.get("/api/stats").json()["frames"], 1)

    def test_rejects_invalid_dataset_class_map(self):
        response = self.client.post(
            "/api/datasets",
            json={
                "name": "D-Fire",
                "version": "bad-map",
                "source_url": "https://example.com/d-fire",
                "license_name": "See source terms",
                "class_map": {"0": "fire", "1": "other"},
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            self.client.get("/api/stats").json()["dataset_versions"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
