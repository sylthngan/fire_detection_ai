
from collections import deque


class FireConfirmation:
    def __init__(
        self,
        window_size=5,
        required_fire_frames=3,
        confidence_threshold=0.5,
        fire_confidence_threshold=None,
        smoke_confidence_threshold=None,
    ):
        if window_size < 1 or not 1 <= required_fire_frames <= window_size:
            raise ValueError("Invalid confirmation settings")

        fire_threshold = (
            confidence_threshold
            if fire_confidence_threshold is None
            else fire_confidence_threshold
        )
        smoke_threshold = (
            confidence_threshold
            if smoke_confidence_threshold is None
            else smoke_confidence_threshold
        )
        if not 0.0 <= fire_threshold <= 1.0:
            raise ValueError("Fire confidence threshold must be between 0 and 1")
        if not 0.0 <= smoke_threshold <= 1.0:
            raise ValueError("Smoke confidence threshold must be between 0 and 1")

        self.fire_window = deque(maxlen=window_size)
        self.smoke_window = deque(maxlen=window_size)

        self.required_fire_frames = required_fire_frames
        self.fire_confidence_threshold = fire_threshold
        self.smoke_confidence_threshold = smoke_threshold

    def update(self, fire_confidence, smoke_confidence=0.0):
        is_fire = fire_confidence >= self.fire_confidence_threshold
        is_smoke = smoke_confidence >= self.smoke_confidence_threshold

        self.fire_window.append(is_fire)
        self.smoke_window.append(is_smoke)

        fire_count = sum(self.fire_window)
        smoke_count = sum(self.smoke_window)

        fire_confirmed = (
            fire_count >= self.required_fire_frames
        )
        smoke_confirmed = (
            smoke_count >= self.required_fire_frames
        )

        return {
            "fire_detected": is_fire,
            "smoke_detected": is_smoke,
            "fire_confirmed": fire_confirmed,
            "smoke_confirmed": smoke_confirmed,
            "fire_count": fire_count,
            "smoke_count": smoke_count
        }
