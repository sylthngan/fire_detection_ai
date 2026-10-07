import argparse
import json
from pathlib import Path

from CSDL.models.database import FireEyesDB


PROJECT_ROOT = Path(__file__).resolve().parent


def run_demo(db):
    """Tạo dữ liệu giả lập để kiểm tra luồng lưu CSDL."""
    ids = db.seed_demo()

    # Dữ liệu giả lập, không phải kết quả chạy nhận diện.
    box = {
        "class_id": 0,
        "confidence": 0.87,
        "xc": 0.5,
        "yc": 0.5,
        "w": 0.2,
        "h": 0.3,
    }

    frame_id = db.record_frame(
        ids["camera_id"],
        ids["model_id"],
        "demo-frame-001",
        "2026-09-30T01:00:00+07:00",
        [box],
    )

    detection_id = db.frame_detections(frame_id)[0]["id"]

    incident_id = db.open_incident(
        detection_id,
        "MANUAL DEMO: synthetic smoke detection",
    )

    db.simulate_notification(
        incident_id,
        ids["contact_id"],
    )

    return {
        "message": (
            "DEMO CSDL: du lieu gia lap; "
            "khong chay AI, khong gui SMS hoac goi dien."
        ),
        "stats": db.counts(),
        "incidents": db.list_incidents(),
    }


def main():
    parser = argparse.ArgumentParser(
        description="FireEyes - Quan ly va kiem thu co so du lieu"
    )

    parser.add_argument(
        "command",
        nargs="?",
        default="stats",
        choices=["init", "demo", "stats", "incidents"],
        help="Thao tac CSDL; mac dinh: stats",
    )

    parser.add_argument(
        "--db",
        type=Path,
        default=PROJECT_ROOT / "data" / "fireeyes.db",
        help="Duong dan file SQLite",
    )

    args = parser.parse_args()

    db = FireEyesDB(args.db)
    db.initialize()

    if args.command == "init":
        print("Schema v1 ready:", db.path)
        return

    if args.command == "demo":
        result = run_demo(db)
    elif args.command == "stats":
        result = db.counts()
    else:
        result = db.list_incidents()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()