
import json
from pathlib import Path


def save_detection(result, path="output/detection_history.json"):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        with output_path.open("r", encoding="utf-8") as f:
            history = json.load(f)

        if not isinstance(history, list):
            raise ValueError("JSON history must be a list")
    else:
        history = []

    history.append(result.to_dict())

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(
            history,
            f,
            indent=4,
            ensure_ascii=False
        )

    return output_path
