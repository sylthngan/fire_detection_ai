
from datetime import datetime
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field


app = FastAPI(title="Fire Detection API")

detections = []


class DetectionPayload(BaseModel):
    camera_id: str
    location: str
    fire_detected: bool
    smoke_detected: bool
    confidence: float = Field(ge=0, le=1)
    confirmed: bool
    timestamp: datetime


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/detections", status_code=201)
def create_detection(data: DetectionPayload):
    record = data.model_dump(mode="json")
    record["id"] = len(detections) + 1

    detections.append(record)

    print("[BACKEND] Detection received:", record)

    return {
        "message": "Detection received",
        "id": record["id"]
    }


@app.get("/api/detections")
def get_detections():
    return detections
