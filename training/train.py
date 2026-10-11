import argparse
from pathlib import Path

from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(
        description="Train a YOLO fire/smoke detector on D-Fire."
    )
    parser.add_argument("--model", type=Path, default=PROJECT_ROOT / "yolo11n.pt")
    parser.add_argument("--data", type=Path, default=PROJECT_ROOT / "D-Fire/data.yaml")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--image-size", type=int, default=416)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--project", type=Path, default=PROJECT_ROOT / "runs/detect")
    parser.add_argument("--name", default="fire_ai")
    args = parser.parse_args()

    if not args.model.is_file():
        raise FileNotFoundError(f"Initial YOLO weights not found: {args.model}")
    if not args.data.is_file():
        raise FileNotFoundError(f"Dataset configuration not found: {args.data}")
    if args.epochs < 1 or args.image_size < 1 or args.batch < 1:
        raise ValueError("epochs, image-size, and batch must be positive")
    if args.workers < 0:
        raise ValueError("workers cannot be negative")

    model = YOLO(str(args.model))
    model.train(
        data=str(args.data),
        epochs=args.epochs,
        imgsz=args.image_size,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        project=str(args.project),
        name=args.name,
        pretrained=True,
        val=True,
        plots=True,
    )


if __name__ == "__main__":
    main()
