import argparse
import json
from pathlib import Path

import numpy as np
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "configs" / "detection_thresholds.json"


def select_class_thresholds(
    class_names,
    thresholds,
    precision,
    recall,
    f1,
    baseline_threshold=0.5,
):
    class_thresholds = {}
    baseline_index = int(np.argmin(np.abs(thresholds - baseline_threshold)))

    for class_index, class_name in class_names.items():
        normalized_name = class_name.strip().lower()
        if normalized_name not in {"fire", "smoke"}:
            raise ValueError(f"Unexpected detection class: {class_name}")

        best_index = int(np.argmax(f1[class_index]))
        class_thresholds[normalized_name] = {
            "confidence_threshold": round(float(thresholds[best_index]), 4),
            "precision": round(float(precision[class_index, best_index]), 4),
            "recall": round(float(recall[class_index, best_index]), 4),
            "f1": round(float(f1[class_index, best_index]), 4),
            "shared_threshold_baseline": {
                "confidence_threshold": round(
                    float(thresholds[baseline_index]), 4
                ),
                "precision": round(
                    float(precision[class_index, baseline_index]), 4
                ),
                "recall": round(float(recall[class_index, baseline_index]), 4),
                "f1": round(float(f1[class_index, baseline_index]), 4),
            },
        }

    if set(class_thresholds) != {"fire", "smoke"}:
        raise ValueError(
            f"Expected Fire and Smoke validation curves, got {sorted(class_thresholds)}"
        )
    return class_thresholds


def main():
    parser = argparse.ArgumentParser(
        description="Choose per-class confidence thresholds by validation F1."
    )
    parser.add_argument("--model", type=Path, default=PROJECT_ROOT / "models/best.pt")
    parser.add_argument("--data", type=Path, default=PROJECT_ROOT / "D-Fire/data.yaml")
    parser.add_argument("--image-size", type=int, default=416)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not args.model.is_file():
        raise FileNotFoundError(f"YOLO model not found: {args.model}")
    if not args.data.is_file():
        raise FileNotFoundError(f"Dataset configuration not found: {args.data}")
    if args.image_size < 1:
        raise ValueError("image-size must be positive")

    model = YOLO(str(args.model))
    metrics = model.val(
        data=str(args.data),
        split="val",
        imgsz=args.image_size,
        device=args.device,
        conf=0.001,
        plots=False,
        verbose=False,
    )

    metric = metrics.box
    thresholds = np.asarray(metric.px)
    precision = np.asarray(metric.p_curve)
    recall = np.asarray(metric.r_curve)
    f1 = np.asarray(metric.f1_curve)
    class_thresholds = select_class_thresholds(
        metrics.names,
        thresholds,
        precision,
        recall,
        f1,
    )

    resolved_model_path = args.model.resolve()
    try:
        model_reference = resolved_model_path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        model_reference = str(resolved_model_path)

    output = {
        "model": model_reference,
        "calibration_split": "val",
        "selection_method": "per-class maximum F1",
        "image_size": args.image_size,
        "classes": class_thresholds,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("\n===== VALIDATION-CALIBRATED THRESHOLDS =====")
    for class_name, result in class_thresholds.items():
        print(
            f"{class_name}: confidence={result['confidence_threshold']:.4f}, "
            f"precision={result['precision']:.4f}, "
            f"recall={result['recall']:.4f}, f1={result['f1']:.4f}"
        )
        baseline = result["shared_threshold_baseline"]
        print(
            f"  shared 0.5: precision={baseline['precision']:.4f}, "
            f"recall={baseline['recall']:.4f}, f1={baseline['f1']:.4f}"
        )
    print(f"Saved threshold configuration: {args.output}")


if __name__ == "__main__":
    main()
