
import time

import requests


class DetectionAPIClient:
    def __init__(
        self,
        camera_id,
        model_id,
        base_url="http://127.0.0.1:8000",
        timeout=2
    ):
        if camera_id < 1 or model_id < 1:
            raise ValueError("camera_id and model_id must be positive")
        self.endpoint = base_url.rstrip("/") + "/api/detections"
        self.camera_id = camera_id
        self.model_id = model_id
        self.timeout = timeout
        self.heartbeat_endpoint = (
            base_url.rstrip("/")
            + f"/api/cameras/{camera_id}/heartbeat"
        )
        self._last_heartbeat = None

    def send_detection(self, event, detections):
        payload = {
            "camera_id": self.camera_id,
            "model_id": self.model_id,
            "request_id": f"{self.camera_id}:{event.timestamp}",
            "captured_at": event.timestamp,
            "detections": detections,
            "confirmed_classes": [
                name
                for name in ("fire", "smoke")
                if getattr(event, f"{name}_detected")
            ],
            "snapshot_path": event.image_path,
        }
        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            print(f"[API] Send failed: {error}")
            return False

        result = response.json()
        print(
            f"[API] Stored frame {result['frame_id']}; "
            f"incident={result['incident_id']}"
        )
        return True

    def send_heartbeat(self):
        try:
            response = requests.post(
                self.heartbeat_endpoint,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            print(f"[API] Camera heartbeat failed: {error}")
            return False
        self._last_heartbeat = time.monotonic()
        return True

    def heartbeat_if_due(self, interval_seconds=15):
        now = time.monotonic()
        if (
            self._last_heartbeat is None
            or now - self._last_heartbeat >= interval_seconds
        ):
            return self.send_heartbeat()
        return True
