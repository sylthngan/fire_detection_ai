import argparse
import json
from pathlib import Path

import cv2
from ultralytics import YOLO

from detection.fire_logic import FireConfirmation
from detection.monitor import DetectionMonitor
from services.api_client import DetectionAPIClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = PROJECT_ROOT / "models" / "best.pt"
DEFAULT_THRESHOLD_CONFIG = (
    PROJECT_ROOT / "configs" / "detection_thresholds.json"
)


def _read_confidence_thresholds(path):
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Confidence threshold configuration not found: {config_path}. "
            "Run `python -m training.calibrate_thresholds` first."
        )

    with config_path.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    try:
        thresholds = {
            name: float(config["classes"][name]["confidence_threshold"])
            for name in ("fire", "smoke")
        }
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"Invalid Fire/Smoke thresholds in {config_path}"
        ) from error

    if any(not 0.0 <= threshold <= 1.0 for threshold in thresholds.values()):
        raise ValueError(
            f"Confidence thresholds in {config_path} must be between 0 and 1"
        )
    return thresholds


def run_detection(
    source=0,
    model_path=DEFAULT_MODEL,
    camera_id="CAM-001",
    location="Laptop Webcam",
    api_url="http://127.0.0.1:8000",
    backend_camera_id=None,
    backend_model_id=None,
    confidence_threshold=None,
    fire_confidence_threshold=None,
    smoke_confidence_threshold=None,
    threshold_config=DEFAULT_THRESHOLD_CONFIG,
    window_size=5,
    required_frames=3,
    image_size=416,
    display=True,
    history_path=PROJECT_ROOT / "output" / "detection_history.json",
    screenshot_dir=PROJECT_ROOT / "output" / "screenshots",
    max_frames=None,
):
    if max_frames is not None and max_frames < 1:
        raise ValueError("max_frames must be positive")
    if (backend_camera_id is None) != (backend_model_id is None):
        raise ValueError(
            "backend-camera-id and backend-model-id must be provided together"
        )

    model_path = Path(model_path)
    if not model_path.is_file():
        raise FileNotFoundError(f"YOLO model not found: {model_path}")

    model = YOLO(str(model_path))
    calibrated_thresholds = _read_confidence_thresholds(threshold_config)
    shared_threshold = (
        confidence_threshold
        if confidence_threshold is not None
        else None
    )
    fire_threshold = (
        fire_confidence_threshold
        if fire_confidence_threshold is not None
        else shared_threshold
        if shared_threshold is not None
        else calibrated_thresholds["fire"]
    )
    smoke_threshold = (
        smoke_confidence_threshold
        if smoke_confidence_threshold is not None
        else shared_threshold
        if shared_threshold is not None
        else calibrated_thresholds["smoke"]
    )
    confirmation = FireConfirmation(
        window_size=window_size,
        required_fire_frames=required_frames,
        confidence_threshold=0.5,
        fire_confidence_threshold=fire_threshold,
        smoke_confidence_threshold=smoke_threshold,
    )
    inference_threshold = min(fire_threshold, smoke_threshold)
    api_client = None
    if backend_camera_id is not None and backend_model_id is not None:
        api_client = DetectionAPIClient(
            camera_id=backend_camera_id,
            model_id=backend_model_id,
            base_url=api_url,
        )
        print(
            "Sending confirmed alerts to backend with "
            f"camera_id={backend_camera_id}, model_id={backend_model_id}."
        )
    else:
        print(
            "Backend sending is disabled. Provide both "
            "--backend-camera-id and --backend-model-id to enable it."
        )
    monitor = DetectionMonitor(
        model=model,
        confirmation=confirmation,
        camera_id=camera_id,
        location=location,
        api_client=api_client,
        image_size=image_size,
        inference_threshold=inference_threshold,
        history_path=history_path,
        screenshot_dir=screenshot_dir,
    )

    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        capture.release()
        raise RuntimeError(f"Cannot open video source: {source}")

    is_camera = isinstance(source, int)
    print(
        f"Monitoring {'camera' if is_camera else source}. "
        + ("Press Q to exit." if display else "Press Ctrl+C to stop.")
    )
    try:
        frames_processed = 0
        while True:
            success, frame = capture.read()
            if not success or frame is None:
                if is_camera:
                    raise RuntimeError("Camera opened but failed to provide a frame")
                print("Video finished.")
                break

            annotated, state = monitor.process_frame(frame)
            frames_processed += 1
            if display:
                status = (
                    "FIRE ALERT" if state["fire_confirmed"]
                    else "SMOKE ALERT" if state["smoke_confirmed"]
                    else "MONITORING"
                )
                color = (
                    (0, 0, 255) if state["fire_confirmed"]
                    else (0, 165, 255) if state["smoke_confirmed"]
                    else (0, 255, 0)
                )
                cv2.putText(
                    annotated,
                    status,
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    color,
                    2,
                )
                cv2.imshow("Fire Detection AI", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            if max_frames is not None and frames_processed >= max_frames:
                break
    finally:
        capture.release()
        if display:
            cv2.destroyAllWindows()
        print("Detection stopped.")


def _parse_source(value):
    try:
        return int(value)
    except ValueError:
        return value


def main():
    parser = argparse.ArgumentParser(
        description="Detect fire and smoke from a webcam or video file."
    )
    parser.add_argument(
        "--source",
        default="0",
        help="Camera index (default: 0) or path to a video file.",
    )
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--camera-id", default="CAM-001")
    parser.add_argument("--location", default="Laptop Webcam")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--backend-camera-id",
        type=int,
        help="Registered camera ID; enables sending confirmed events to backend.",
    )
    parser.add_argument(
        "--backend-model-id",
        type=int,
        help="Registered model ID; required with --backend-camera-id.",
    )
    parser.add_argument(
        "--threshold-config",
        type=Path,
        default=DEFAULT_THRESHOLD_CONFIG,
        help="Validation-calibrated per-class thresholds JSON.",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        help="Override both class-specific confidence thresholds.",
    )
    parser.add_argument(
        "--fire-confidence-threshold",
        type=float,
        help="Override the shared threshold for fire detections.",
    )
    parser.add_argument(
        "--smoke-confidence-threshold",
        type=float,
        help="Override the shared threshold for smoke detections.",
    )
    parser.add_argument("--window-size", type=int, default=5)
    parser.add_argument("--required-frames", type=int, default=3)
    parser.add_argument("--image-size", type=int, default=416)
    parser.add_argument(
        "--history-path",
        type=Path,
        default=PROJECT_ROOT / "output" / "detection_history.json",
    )
    parser.add_argument(
        "--screenshot-dir",
        type=Path,
        default=PROJECT_ROOT / "output" / "screenshots",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        help="Stop after processing this many frames.",
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Run without opening a preview window.",
    )
    args = parser.parse_args()

    run_detection(
        source=_parse_source(args.source),
        model_path=args.model,
        camera_id=args.camera_id,
        location=args.location,
        api_url=args.api_url,
        backend_camera_id=args.backend_camera_id,
        backend_model_id=args.backend_model_id,
        confidence_threshold=args.confidence_threshold,
        fire_confidence_threshold=args.fire_confidence_threshold,
        smoke_confidence_threshold=args.smoke_confidence_threshold,
        threshold_config=args.threshold_config,
        window_size=args.window_size,
        required_frames=args.required_frames,
        image_size=args.image_size,
        display=not args.no_display,
        history_path=args.history_path,
        screenshot_dir=args.screenshot_dir,
        max_frames=args.max_frames,
    )


def run_webcam(camera_index=0):
    run_detection(source=camera_index)


if __name__ == "__main__":
    main()
