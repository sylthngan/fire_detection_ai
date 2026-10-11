import argparse
import json
from pathlib import Path

import numpy as np
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_THRESHOLD_CONFIG = (
    PROJECT_ROOT / "configs" / "detection_thresholds.json"
)


def metrics_at_threshold(metric, class_index, threshold):
    thresholds = np.asarray(metric.px)
    point_index = int(np.argmin(np.abs(thresholds - threshold)))
    precision = float(metric.p_curve[class_index][point_index])
    recall = float(metric.r_curve[class_index][point_index])
    f1 = float(metric.f1_curve[class_index][point_index])
    return {
        "threshold": float(thresholds[point_index]),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate the fire/smoke model on the D-Fire test split."
    )
    parser.add_argument("--model", type=Path, default=PROJECT_ROOT / "models/best.pt")
    parser.add_argument("--data", type=Path, default=PROJECT_ROOT / "D-Fire/data.yaml")
    parser.add_argument("--image-size", type=int, default=416)
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--threshold-config",
        type=Path,
        default=DEFAULT_THRESHOLD_CONFIG,
        help="Per-class thresholds calibrated on the validation split.",
    )
    args = parser.parse_args()

    if not args.model.is_file():
        raise FileNotFoundError(f"YOLO model not found: {args.model}")
    if not args.data.is_file():
        raise FileNotFoundError(f"Dataset configuration not found: {args.data}")
    if not args.threshold_config.is_file():
        raise FileNotFoundError(
            f"Threshold configuration not found: {args.threshold_config}. "
            "Run `python -m training.calibrate_thresholds` first."
        )

    with args.threshold_config.open("r", encoding="utf-8") as config_file:
        threshold_config = json.load(config_file)
    try:
        calibrated_thresholds = {
            class_name: float(
                threshold_config["classes"][class_name]["confidence_threshold"]
            )
            for class_name in ("fire", "smoke")
        }
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"Threshold configuration must define Fire and Smoke: "
            f"{args.threshold_config}"
        ) from error
    if any(
        not 0.0 <= threshold <= 1.0
        for threshold in calibrated_thresholds.values()
    ):
        raise ValueError("Confidence thresholds must be between 0 and 1")

    model = YOLO(str(args.model))
    metrics = model.val(
        data=str(args.data),
        split="test",
        imgsz=args.image_size,
        device=args.device,
        conf=0.001,
    )
    class_metrics = {}
    print("\n===== TEST SET CLASS METRICS =====")
    print(
        "Class | F1-optimal P/R/AP50/AP50-95 | "
        "Validation-calibrated threshold P/R/F1 | Shared 0.5 P/R/F1"
    )
    for metric_index, class_id in enumerate(metrics.box.ap_class_index):
        class_name = metrics.names[int(class_id)].strip().lower()
        if class_name not in calibrated_thresholds:
            raise ValueError(
                f"No validation threshold configured for class {class_name}"
            )

        calibrated = metrics_at_threshold(
            metrics.box,
            metric_index,
            calibrated_thresholds[class_name],
        )
        baseline = metrics_at_threshold(metrics.box, metric_index, 0.5)
        precision, recall, map50, map_all = metrics.box.class_result(metric_index)
        class_metrics[class_name] = {
            "f1_optimal": {
                "precision": float(precision),
                "recall": float(recall),
                "map50": float(map50),
                "map50_95": float(map_all),
            },
            "validation_calibrated": calibrated,
            "shared_threshold_baseline": baseline,
        }
        print(
            f"{class_name}: "
            f"{precision:.4f}/{recall:.4f}/{map50:.4f}/{map_all:.4f} | "
            f"{calibrated['threshold']:.4f}: "
            f"{calibrated['precision']:.4f}/{calibrated['recall']:.4f}/"
            f"{calibrated['f1']:.4f} | "
            f"0.5: {baseline['precision']:.4f}/{baseline['recall']:.4f}/"
            f"{baseline['f1']:.4f}"
        )

    print("\n===== TEST SET RESULTS =====")
    print(f"Precision: {metrics.box.mp:.4f}")
    print(f"Recall: {metrics.box.mr:.4f}")
    print(f"mAP50: {metrics.box.map50:.4f}")
    print(f"mAP50-95: {metrics.box.map:.4f}")
    report_path = Path(metrics.save_dir) / "evaluation.json"
    report_path.write_text(
        json.dumps(
            {
                "model": str(args.model),
                "split": "test",
                "threshold_calibration_split": threshold_config.get(
                    "calibration_split"
                ),
                "threshold_selection_method": threshold_config.get(
                    "selection_method"
                ),
                "overall": {
                    "precision": float(metrics.box.mp),
                    "recall": float(metrics.box.mr),
                    "map50": float(metrics.box.map50),
                    "map50_95": float(metrics.box.map),
                },
                "classes": class_metrics,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Detailed class metrics saved to: {report_path}")


if __name__ == "__main__":
    main()