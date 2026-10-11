import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Path as PathParam,
    Query,
    Request,
    status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.CSDL.models.database import (
    CameraUnavailableError,
    FireEyesDB,
    IncidentAlreadyClosedError,
    IdempotencyConflictError,
    ModelReferenceError,
    RecordNotFoundError,
)


DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "fireeyes.db"
DEFAULT_SNAPSHOT_ROOT = (
    Path(__file__).resolve().parents[1] / "output" / "screenshots"
)
ALLOWED_SNAPSHOT_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class DetectionBox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_id: int = Field(strict=True, ge=0, le=1)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    xc: float = Field(ge=0, le=1, allow_inf_nan=False)
    yc: float = Field(ge=0, le=1, allow_inf_nan=False)
    w: float = Field(gt=0, le=1, allow_inf_nan=False)
    h: float = Field(gt=0, le=1, allow_inf_nan=False)


class FrameIngest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_id: int = Field(strict=True, gt=0)
    model_id: int = Field(strict=True, gt=0)
    request_id: str = Field(min_length=1, max_length=200)
    captured_at: str = Field(min_length=1)
    detections: list[DetectionBox] = Field(max_length=500)
    confirmed_classes: list[Literal["fire", "smoke"]] = Field(
        default_factory=list,
        max_length=2,
    )
    snapshot_path: str | None = Field(default=None, max_length=2048)

    @field_validator("confirmed_classes")
    @classmethod
    def confirmed_classes_are_unique(
        cls,
        value: list[str],
    ) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("confirmed_classes must not contain duplicates")
        return value


class FrameIngestResponse(BaseModel):
    frame_id: int
    status: str
    incident_id: int | None = None


class LocationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=500)


class CameraCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: int = Field(strict=True, gt=0)
    name: str = Field(min_length=1, max_length=200)
    source_ref: str = Field(
        min_length=1,
        max_length=500,
        description="A local source label/path; never include camera credentials.",
    )


class CameraStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class AlertAcknowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledged_by: str = Field(min_length=1, max_length=100)


class AlertResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["resolved", "false_alarm"]
    note: str = Field(min_length=1, max_length=1000)


class DatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    source_url: str = Field(min_length=1, max_length=1000)
    license_name: str = Field(min_length=1, max_length=200)
    class_map: dict[str, str]
    manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-fA-F]{64}$",
    )

    @field_validator("class_map")
    @classmethod
    def validate_class_map(cls, value: dict[str, str]) -> dict[str, str]:
        if set(value) != {"0", "1"} or set(value.values()) != {"fire", "smoke"}:
            raise ValueError(
                "class_map must map IDs 0 and 1 to fire and smoke exactly once"
            )
        return value


class ModelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    dataset_id: int = Field(strict=True, gt=0)
    weights_path: str = Field(min_length=1, max_length=2048)
    weights_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class CreatedResponse(BaseModel):
    id: int
    status: str = "created"


def get_db(request: Request) -> FireEyesDB:
    return request.app.state.db


def create_app(
    db_path: Path | str | None = None,
    snapshot_root: Path | str | None = None,
) -> FastAPI:
    database_path = Path(
        db_path or os.environ.get("FIREEYES_DB_PATH", DEFAULT_DB_PATH)
    )
    allowed_snapshot_root = Path(
        snapshot_root or os.environ.get(
            "FIREEYES_SNAPSHOT_ROOT",
            DEFAULT_SNAPSHOT_ROOT,
        )
    ).resolve()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = FireEyesDB(database_path)
        db.initialize()
        app.state.db = db
        yield

    app = FastAPI(
        title="FireEyes Backend API",
        description="Local API for storing AI frame detections in SQLite.",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/api/locations",
        response_model=CreatedResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_location(
        payload: LocationCreate,
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> CreatedResponse:
        try:
            record_id = db.create_location(
                payload.name.strip(),
                payload.address.strip(),
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A location with this name already exists",
            ) from error
        return CreatedResponse(id=record_id)

    @app.get("/api/locations")
    def list_locations(
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> list[dict[str, object]]:
        return db.list_locations()

    @app.post(
        "/api/cameras",
        response_model=CreatedResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_camera(
        payload: CameraCreate,
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> CreatedResponse:
        try:
            record_id = db.create_camera(
                payload.location_id,
                payload.name.strip(),
                payload.source_ref.strip(),
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="location_id is invalid or camera name already exists there",
            ) from error
        return CreatedResponse(id=record_id)

    @app.get("/api/cameras")
    def list_cameras(
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> list[dict[str, object]]:
        return db.list_cameras()

    @app.get("/api/cameras/{camera_id}/status")
    def camera_status(
        camera_id: Annotated[int, PathParam(gt=0)],
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> dict[str, object]:
        camera = db.get_camera_status(camera_id)
        if camera is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Camera not found",
            )
        return camera

    @app.patch("/api/cameras/{camera_id}/status")
    def update_camera_status(
        camera_id: Annotated[int, PathParam(gt=0)],
        payload: CameraStatusUpdate,
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> dict[str, object]:
        try:
            return db.set_camera_enabled(camera_id, payload.enabled)
        except RecordNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Camera not found",
            ) from error

    @app.post("/api/cameras/{camera_id}/heartbeat")
    def camera_heartbeat(
        camera_id: Annotated[int, PathParam(gt=0)],
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> dict[str, str]:
        try:
            last_seen_at = db.record_camera_heartbeat(camera_id)
        except RecordNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Camera not found",
            ) from error
        except CameraUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        return {"status": "received", "last_seen_at": last_seen_at}

    @app.post(
        "/api/datasets",
        response_model=CreatedResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_dataset(
        payload: DatasetCreate,
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> CreatedResponse:
        try:
            record_id = db.create_dataset(
                name=payload.name.strip(),
                version=payload.version.strip(),
                source_url=payload.source_url.strip(),
                license_name=payload.license_name.strip(),
                class_map={
                    int(class_id): class_name
                    for class_id, class_name in payload.class_map.items()
                },
                manifest_sha256=payload.manifest_sha256,
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A dataset with this name and version already exists",
            ) from error
        return CreatedResponse(id=record_id)

    @app.get("/api/datasets")
    def list_datasets(
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> list[dict[str, object]]:
        return db.list_datasets()

    @app.post(
        "/api/models",
        response_model=CreatedResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_model(
        payload: ModelCreate,
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> CreatedResponse:
        try:
            record_id = db.create_model(
                name=payload.name.strip(),
                dataset_id=payload.dataset_id,
                weights_path=payload.weights_path.strip(),
                weights_sha256=payload.weights_sha256.lower(),
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="dataset_id is invalid or model name already exists",
            ) from error
        return CreatedResponse(id=record_id)

    @app.get("/api/models")
    def list_models(
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> list[dict[str, object]]:
        return db.list_models()

    @app.post(
        "/api/detections",
        response_model=FrameIngestResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @app.post(
        "/api/frames",
        response_model=FrameIngestResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def ingest_frame(
        payload: FrameIngest,
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> FrameIngestResponse:
        class_ids = {"smoke": 0, "fire": 1}
        confirmed_class_ids = {
            class_ids[class_name] for class_name in payload.confirmed_classes
        }
        available_class_ids = {
            detection.class_id for detection in payload.detections
        }
        if not confirmed_class_ids.issubset(available_class_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Each confirmed class must have a matching detection box",
            )

        try:
            frame_id = db.record_frame(
                camera_id=payload.camera_id,
                model_id=payload.model_id,
                request_id=payload.request_id,
                captured_at=payload.captured_at,
                detections=[
                    detection.model_dump() for detection in payload.detections
                ],
                snapshot_path=payload.snapshot_path,
            )
            incident_id = None
            if confirmed_class_ids:
                stored_detections = db.frame_detections(frame_id)
                evidence = max(
                    (
                        detection
                        for detection in stored_detections
                        if detection["class_id"] in confirmed_class_ids
                    ),
                    key=lambda detection: detection["confidence"],
                )
                alert_names = ", ".join(
                    name for name in ("fire", "smoke")
                    if name in payload.confirmed_classes
                )
                incident_id = db.open_incident(
                    evidence["id"],
                    f"AI confirmed {alert_names} across multiple frames",
                )
        except IdempotencyConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except ModelReferenceError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except CameraUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
        except sqlite3.IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="camera_id or model_id does not reference a valid record",
            ) from error

        return FrameIngestResponse(
            frame_id=frame_id,
            status="stored",
            incident_id=incident_id,
        )

    @app.get("/api/stats")
    def stats(
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> dict[str, int]:
        return db.counts()

    @app.get("/api/incidents")
    def incidents(
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> list[dict[str, object]]:
        return db.list_incidents()

    @app.get("/api/detections/history")
    def detection_history(
        db: Annotated[FireEyesDB, Depends(get_db)],
        camera_id: Annotated[int | None, Query(gt=0)] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[dict[str, object]]:
        return db.list_detection_history(camera_id, limit, offset)

    @app.get("/api/alerts")
    def alerts(
        db: Annotated[FireEyesDB, Depends(get_db)],
        acknowledged: bool | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[dict[str, object]]:
        return db.list_incidents(acknowledged, limit, offset)

    @app.get("/api/alerts/latest")
    def latest_alert(
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> dict[str, object] | None:
        alerts = db.list_incidents(limit=1)
        return alerts[0] if alerts else None

    @app.get("/api/alerts/{alert_id}/snapshot")
    def alert_snapshot(
        alert_id: Annotated[int, PathParam(gt=0)],
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> FileResponse:
        alert = db.get_incident(alert_id)
        if alert is None or not alert["snapshot_path"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Snapshot not found",
            )
        try:
            snapshot_path = Path(str(alert["snapshot_path"])).resolve(strict=True)
            snapshot_path.relative_to(allowed_snapshot_root)
        except (OSError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Snapshot not found",
            ) from None
        if (
            not snapshot_path.is_file()
            or snapshot_path.suffix.lower() not in ALLOWED_SNAPSHOT_SUFFIXES
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Snapshot not found",
            )
        return FileResponse(
            snapshot_path,
            media_type={
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
            }[snapshot_path.suffix.lower()],
            headers={"Cache-Control": "no-store"},
        )

    @app.patch("/api/alerts/{alert_id}/acknowledge")
    def acknowledge_alert(
        alert_id: Annotated[int, PathParam(gt=0)],
        payload: AlertAcknowledge,
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> dict[str, object]:
        try:
            result = db.acknowledge_incident(
                alert_id,
                payload.acknowledged_by,
            )
        except RecordNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert not found",
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
        return result

    @app.patch("/api/alerts/{alert_id}/resolve")
    def resolve_alert(
        alert_id: Annotated[int, PathParam(gt=0)],
        payload: AlertResolution,
        db: Annotated[FireEyesDB, Depends(get_db)],
    ) -> dict[str, object]:
        if not payload.note.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A resolution note is required",
            )
        try:
            result = db.close_incident(
                alert_id,
                payload.status,
                payload.note.strip(),
            )
        except RecordNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert not found",
            ) from error
        except IncidentAlreadyClosedError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
        return result

    return app


app = create_app()
