import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.CSDL.models.database import FireEyesDB
from detection.fire_logic import FireConfirmation
from detection.monitor import DetectionMonitor
from detection.webcam import _read_confidence_thresholds
from services.api_client import DetectionAPIClient
from training.calibrate_thresholds import select_class_thresholds
from training.evaluate import metrics_at_threshold


class FakeBox:
    def __init__(self, class_id, confidence):
        self.cls = SimpleNamespace(item=lambda: class_id)
        self.conf = SimpleNamespace(item=lambda: confidence)
        self.xywhn = np.array([[0.5, 0.5, 0.2, 0.2]])


class FakeModel:
    names = {0: "Fire", 1: "Smoke"}

    def __init__(self, frame_predictions):
        self.frame_predictions = iter(frame_predictions)

    def predict(self, **kwargs):
        self.last_call = kwargs
        boxes = next(self.frame_predictions)
        frame = np.zeros((16, 16, 3), dtype=np.uint8)
        result = SimpleNamespace(
            boxes=boxes,
            plot=lambda: frame.copy(),
        )
        return [result]


class FakeAPIClient:
    def __init__(self):
        self.events = []
        self.heartbeats = 0

    def heartbeat_if_due(self):
        self.heartbeats += 1
        return True

    def send_detection(self, event, detections):
        self.events.append((event.to_dict(), detections))
        return True


class FireConfirmationTests(unittest.TestCase):
    def test_evaluation_reads_class_metrics_at_nearest_confidence(self):
        metric = SimpleNamespace(
            px=np.array([0.2, 0.5, 0.8]),
            p_curve=np.array([[0.7, 0.8, 0.9]]),
            r_curve=np.array([[0.8, 0.6, 0.3]]),
            f1_curve=np.array([[0.7467, 0.6857, 0.45]]),
        )

        result = metrics_at_threshold(metric, 0, 0.48)

        self.assertEqual(result["threshold"], 0.5)
        self.assertEqual(result["precision"], 0.8)
        self.assertEqual(result["recall"], 0.6)

    def test_threshold_calibration_selects_per_class_maximum_f1(self):
        selected = select_class_thresholds(
            {0: "Fire", 1: "Smoke"},
            np.array([0.2, 0.5]),
            np.array([[0.6, 0.8], [0.5, 0.7]]),
            np.array([[0.8, 0.4], [0.7, 0.3]]),
            np.array([[0.6857, 0.5333], [0.5833, 0.42]]),
        )

        self.assertEqual(
            selected["fire"]["confidence_threshold"],
            0.2,
        )
        self.assertEqual(
            selected["smoke"]["confidence_threshold"],
            0.2,
        )
        self.assertEqual(
            selected["fire"]["shared_threshold_baseline"]["recall"],
            0.4,
        )

    def test_confirms_fire_in_three_of_five_frames(self):
        confirmation = FireConfirmation(window_size=5, required_fire_frames=3)
        states = [
            confirmation.update(confidence, 0.0)
            for confidence in (0.8, 0.2, 0.9, 0.7, 0.1)
        ]

        self.assertFalse(states[0]["fire_confirmed"])
        self.assertTrue(states[3]["fire_confirmed"])
        self.assertTrue(states[4]["fire_confirmed"])

    def test_confirmation_clears_after_positive_frames_leave_window(self):
        confirmation = FireConfirmation(window_size=3, required_fire_frames=2)
        for confidence in (0.9, 0.9, 0.1):
            state = confirmation.update(confidence)
        self.assertTrue(state["fire_confirmed"])

        state = confirmation.update(0.1)
        self.assertFalse(state["fire_confirmed"])

    def test_rejects_invalid_threshold(self):
        with self.assertRaises(ValueError):
            FireConfirmation(confidence_threshold=1.1)

    def test_supports_independent_fire_and_smoke_thresholds(self):
        confirmation = FireConfirmation(
            window_size=1,
            required_fire_frames=1,
            fire_confidence_threshold=0.6,
            smoke_confidence_threshold=0.4,
        )

        state = confirmation.update(0.5, 0.5)

        self.assertFalse(state["fire_detected"])
        self.assertTrue(state["smoke_detected"])

    def test_reads_per_class_thresholds_from_calibration_file(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "thresholds.json"
            config_path.write_text(
                '{"classes": {'
                '"fire": {"confidence_threshold": 0.26},'
                '"smoke": {"confidence_threshold": 0.18}'
                '}}',
                encoding="utf-8",
            )

            self.assertEqual(
                _read_confidence_thresholds(config_path),
                {"fire": 0.26, "smoke": 0.18},
            )


class DetectionMonitorTests(unittest.TestCase):
    def test_saves_and_sends_one_event_when_fire_is_confirmed(self):
        positive = [FakeBox(0, 0.8)]
        model = FakeModel([positive, positive, positive, positive])
        api_client = FakeAPIClient()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            monitor = DetectionMonitor(
                model=model,
                confirmation=FireConfirmation(
                    window_size=3,
                    required_fire_frames=2,
                ),
                api_client=api_client,
                history_path=root / "history.json",
                screenshot_dir=root / "screenshots",
            )

            states = [
                monitor.process_frame(np.zeros((16, 16, 3), dtype=np.uint8))[1]
                for _ in range(4)
            ]

            self.assertFalse(states[0]["fire_confirmed"])
            self.assertTrue(states[1]["fire_confirmed"])
            self.assertEqual(len(api_client.events), 1)
            self.assertEqual(api_client.heartbeats, 4)
            self.assertTrue(api_client.events[0][0]["confirmed"])
            self.assertTrue(api_client.events[0][0]["fire_detected"])
            self.assertEqual(
                api_client.events[0][1][0]["class_id"],
                1,
            )
            self.assertEqual(
                api_client.events[0][1][0]["xc"],
                0.5,
            )
            self.assertTrue((root / "history.json").is_file())
            self.assertEqual(len(list((root / "screenshots").glob("*.jpg"))), 1)

    def test_confirmed_ai_event_reaches_backend_and_creates_ui_incident(self):
        positive = [FakeBox(0, 0.9)]
        model = FakeModel([positive, positive])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = FireEyesDB(root / "fireeyes.db")
            db.initialize()
            ids = db.seed_demo()

            with TestClient(create_app(db.path)) as backend_client:
                def post_to_test_api(url, json=None, timeout=2):
                    if url.endswith("/heartbeat"):
                        return backend_client.post(url)
                    return backend_client.post(url, json=json)

                monitor = DetectionMonitor(
                    model=model,
                    confirmation=FireConfirmation(
                        window_size=2,
                        required_fire_frames=2,
                    ),
                    api_client=DetectionAPIClient(
                        camera_id=ids["camera_id"],
                        model_id=ids["model_id"],
                    ),
                    history_path=root / "history.json",
                    screenshot_dir=root / "screenshots",
                )
                with patch(
                    "services.api_client.requests.post",
                    side_effect=post_to_test_api,
                ):
                    monitor.process_frame(
                        np.zeros((16, 16, 3), dtype=np.uint8)
                    )
                    monitor.process_frame(
                        np.zeros((16, 16, 3), dtype=np.uint8)
                    )

                self.assertEqual(
                    backend_client.get("/api/stats").json()["frames"],
                    1,
                )
                self.assertEqual(
                    backend_client.get(
                        f"/api/cameras/{ids['camera_id']}/status"
                    ).json()["status"],
                    "active",
                )
                incidents = backend_client.get("/api/incidents").json()
                self.assertEqual(len(incidents), 1)
                self.assertEqual(incidents[0]["alert_class"], "fire")
                self.assertEqual(
                    incidents[0]["camera"],
                    "Camera demo",
                )

    def test_overlapping_class_confirmations_send_only_matching_boxes(self):
        fire = FakeBox(0, 0.9)
        smoke = FakeBox(1, 0.85)
        model = FakeModel(
            [
                [fire],
                [fire, smoke],
                [fire, smoke],
                [smoke],
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = FireEyesDB(root / "fireeyes.db")
            db.initialize()
            ids = db.seed_demo()

            with TestClient(create_app(db.path)) as backend_client:
                def post_to_test_api(url, json=None, timeout=2):
                    if url.endswith("/heartbeat"):
                        return backend_client.post(url)
                    return backend_client.post(url, json=json)

                monitor = DetectionMonitor(
                    model=model,
                    confirmation=FireConfirmation(
                        window_size=5,
                        required_fire_frames=3,
                    ),
                    api_client=DetectionAPIClient(
                        camera_id=ids["camera_id"],
                        model_id=ids["model_id"],
                    ),
                    history_path=root / "history.json",
                    screenshot_dir=root / "screenshots",
                )
                with patch(
                    "services.api_client.requests.post",
                    side_effect=post_to_test_api,
                ):
                    states = [
                        monitor.process_frame(
                            np.zeros((16, 16, 3), dtype=np.uint8)
                        )[1]
                        for _ in range(4)
                    ]

                self.assertTrue(states[2]["fire_confirmed"])
                self.assertTrue(states[3]["fire_confirmed"])
                self.assertTrue(states[3]["smoke_confirmed"])
                self.assertEqual(
                    backend_client.get("/api/stats").json()["frames"],
                    2,
                )
                history = backend_client.get("/api/detections/history").json()
                self.assertEqual(
                    [item["detection_class"] for item in history],
                    ["smoke", "fire"],
                )

    def test_smoke_prediction_uses_smoke_class(self):
        model = FakeModel([[FakeBox(1, 0.8)]])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            monitor = DetectionMonitor(
                model=model,
                confirmation=FireConfirmation(
                    window_size=1,
                    required_fire_frames=1,
                ),
                history_path=root / "history.json",
                screenshot_dir=root / "screenshots",
            )

            annotated, state = monitor.process_frame(
                np.zeros((16, 16, 3), dtype=np.uint8)
            )

            self.assertTrue(state["smoke_confirmed"])
            self.assertFalse(state["fire_confirmed"])
            self.assertEqual(annotated.shape, (16, 16, 3))
            self.assertEqual(model.last_call["conf"], 0.25)


if __name__ == "__main__":
    unittest.main()
