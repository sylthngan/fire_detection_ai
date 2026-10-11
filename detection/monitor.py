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

        if new_fire or new_smoke:
            self._record_event(state, confidences, annotated)

        self.previous_fire_confirmed = state["fire_confirmed"]
        self.previous_smoke_confirmed = state["smoke_confirmed"]
        return annotated, state

    def _record_event(self, state, confidences, annotated):
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        image_path = self.screenshot_dir / f"{self.camera_id}_{timestamp}.jpg"
        if not cv2.imwrite(str(image_path), annotated):
            raise OSError(f"Could not save detection image: {image_path}")

        event = create_result(
            fire_detected=state["fire_confirmed"],
            smoke_detected=state["smoke_confirmed"],
            confidence=max(
                confidences["fire"] if state["fire_confirmed"] else 0.0,
                confidences["smoke"] if state["smoke_confirmed"] else 0.0,
            ),
            confirmed=True,
            camera_id=self.camera_id,
            location=self.location,
            image_path=str(image_path),
        )
        save_detection(event, self.history_path)
        print("[AI] Confirmed detection:", event.to_dict())

        if self.api_client is not None:
            if self.api_client.send_detection(event):
                print("[AI] Backend received the detection.")
            else:
                print(
                    "[AI] Detection is saved locally, but backend delivery failed."
                )
