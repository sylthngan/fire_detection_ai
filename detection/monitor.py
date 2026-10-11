from datetime import datetime
from pathlib import Path

import cv2

from detection.fire_logic import FireConfirmation
from models_data.detection_result import create_result
from services.json_output import save_detection


class DetectionMonitor:
    def __init__(
        self,
        model,
        confirmation=None,
        camera_id="CAM-001",
        location="Laptop Webcam",
        api_client=None,
        image_size=416,
        inference_threshold=0.25,
        history_path=Path("output/detection_history.json"),
        screenshot_dir=Path("output/screenshots"),
    ):
        self.model = model
        self.confirmation = confirmation or FireConfirmation()
        self.camera_id = camera_id
        self.location = location
        self.api_client = api_client
        self.image_size = image_size
        self.inference_threshold = inference_threshold
        self.history_path = Path(history_path)
        self.screenshot_dir = Path(screenshot_dir)
        self.previous_fire_confirmed = False
        self.previous_smoke_confirmed = False

    def process_frame(self, frame):
        if self.api_client is not None:
            self.api_client.heartbeat_if_due()

        predictions = self.model.predict(
            source=frame,
            conf=self.inference_threshold,
            imgsz=self.image_size,
            device="cpu",
            verbose=False,
        )
        if not predictions:
            raise RuntimeError("YOLO returned no prediction for the frame")

        result = predictions[0]
        confidences = {"fire": 0.0, "smoke": 0.0}
        for box in result.boxes:
            class_id = int(box.cls.item())
            confidence = float(box.conf.item())
            class_name = str(self.model.names[class_id]).strip().lower()
            if class_name in confidences:
                confidences[class_name] = max(
                    confidences[class_name],
                    confidence,
                )

        state = self.confirmation.update(
            confidences["fire"],
            confidences["smoke"],
        )
        new_fire = (
            state["fire_confirmed"] and not self.previous_fire_confirmed
        )
        new_smoke = (
            state["smoke_confirmed"] and not self.previous_smoke_confirmed
        )
        annotated = result.plot()

        newly_confirmed_classes = {
            name
            for name, is_new in (
                ("fire", new_fire),
                ("smoke", new_smoke),
            )
            if is_new
        }
        if newly_confirmed_classes:
            detection_boxes = self._detection_boxes(
                result.boxes,
                newly_confirmed_classes,
            )
            self._record_event(
                newly_confirmed_classes,
                confidences,
                annotated,
                detection_boxes,
            )

        self.previous_fire_confirmed = state["fire_confirmed"]
        self.previous_smoke_confirmed = state["smoke_confirmed"]
        return annotated, state

    def _detection_boxes(self, boxes, confirmed_classes):
        class_ids = {"smoke": 0, "fire": 1}
        detections = []
        for box in boxes:
            class_index = int(box.cls.item())
            class_name = str(self.model.names[class_index]).strip().lower()
            if class_name not in confirmed_classes:
                continue

            x_center, y_center, width, height = [
                float(value) for value in box.xywhn[0].tolist()
            ]
            detections.append(
                {
                    "class_id": class_ids[class_name],
                    "confidence": float(box.conf.item()),
                    "xc": x_center,
                    "yc": y_center,
                    "w": width,
                    "h": height,
                }
            )
        if not detections:
            raise RuntimeError(
                "A confirmed alert has no matching detection box in this frame"
            )
        return detections

    def _record_event(
        self,
        confirmed_classes,
        confidences,
        annotated,
        detections,
    ):
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        image_path = self.screenshot_dir / f"{self.camera_id}_{timestamp}.jpg"
        if not cv2.imwrite(str(image_path), annotated):
            raise OSError(f"Could not save detection image: {image_path}")

        event = create_result(
            fire_detected="fire" in confirmed_classes,
            smoke_detected="smoke" in confirmed_classes,
            confidence=max(
                confidences[name] for name in confirmed_classes
            ),
            confirmed=True,
            camera_id=self.camera_id,
            location=self.location,
            image_path=str(image_path),
        )
        save_detection(event, self.history_path)
        print("[AI] Confirmed detection:", event.to_dict())

        if self.api_client is not None:
            if not self.api_client.send_detection(event, detections):
                print(
                    "[AI] Detection is saved locally, but backend delivery failed."
                )
