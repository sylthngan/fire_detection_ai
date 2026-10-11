import argparse
from ultralytics import YOLO
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Run YOLO on one image.")
    parser.add_argument("--model", type=Path, default=PROJECT_ROOT / "models/best.pt")
    parser.add_argument(
        "--image",
        type=Path,
        default=PROJECT_ROOT / "D-Fire/test/images/WEB11806.jpg",
    )
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--image-size", type=int, default=416)
    args = parser.parse_args()

    if not args.model.is_file():
        raise FileNotFoundError(f"YOLO model not found: {args.model}")
    if not args.image.is_file():
        raise FileNotFoundError(f"Image not found: {args.image}")

    model = YOLO(str(args.model))
    model.predict(
        source=str(args.image),
        conf=args.confidence,
        imgsz=args.image_size,
        device="cpu",
        save=True,
    )
    print("Image detection completed.")


if __name__ == "__main__":
    main()