
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional


@dataclass
class DetectionResult:
    camera_id: str
    location: str
    fire_detected: bool
    smoke_detected: bool
    confidence: float
    confirmed: bool
    timestamp: str
    image_path: Optional[str] = None

    def to_dict(self):
        return asdict(self)


def create_result(
    fire_detected,
    smoke_detected,
    confidence,
    confirmed,
    camera_id="CAM-001",
    location="Laptop Webcam",
    image_path=None
):
    return DetectionResult(
        camera_id=camera_id,
        location=location,
        fire_detected=bool(fire_detected),
        smoke_detected=bool(smoke_detected),
        confidence=round(float(confidence), 4),
        confirmed=bool(confirmed),
        timestamp=datetime.now().astimezone().isoformat(),
        image_path=image_path
    )
