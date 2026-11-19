from .facial_service import (
    _facial_lock,
    _observations,
    _run_facial_analysis,
)


"""NAO camera API and independent facial emotion observations.

Supports standalone images, session-linked images, live RGB frames,
and ResMaskingNet evaluation. Facial observations never affect
verbal answer correctness.
"""
from .camera_utils import read_image as _read_image
from .camera_utils import save_image
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter, BackgroundTasks, File, Form,
    HTTPException, UploadFile
)
from PIL import Image

import backend
from backend.facial_classifier import (
    FacialInferenceError,
    classify_facial_frame
)
from backend.schemas import FacialResult, ScenarioEvent


router = APIRouter(tags=["Camera / Computer Vision"])

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_RAW_PIXELS = 3_000_000

# One camera target per backend process.
_camera_target = None

# Prevent duplicate inference and observation writes within one process.


# -------------------- Shared Helpers --------------------

def _backend():
    return backend.app


def _now():
    return datetime.now(timezone.utc).isoformat()


def _get_session(session_id, require_active=True):
    session = _backend().sessions.get(session_id)

    if session is None:
        raise HTTPException(404, "Session not found.")

    if require_active and session.get("status") != "active":
        raise HTTPException(409, "Session is not active.")

    return session


def _validate_camera_target(session_id, scenario_id):
    """Require the requested scenario to be active."""
    ctx = _backend()
    session = _get_session(session_id)

    if not any(
        item.get("scenario_id") == scenario_id
        for item in ctx.scenarios_db
    ):
        raise HTTPException(404, "Scenario not found.")

    if (
        session.get("active_scenario_id") != scenario_id
        or session.get("scenario_progress", {})
            .get(str(scenario_id), {})
            .get("status") != "in_progress"
    ):
        raise HTTPException(
            409,
            "Camera target does not match the active scenario. "
            "Rebind the camera."
        )

    return session



def _save_image(image, folder, filename):
    """Save an image using the shared camera utility."""
    return save_image(
        image,
        folder,
        filename,
        _backend().ROOT
    )


def _link_frame(session, scenario_id, image_file, source=None):
    """Attach a camera image to its scenario and existing response."""
    key = str(scenario_id)

    frames = session.setdefault(
        "captured_frames", {}
    ).setdefault(key, [])

    frames.append(image_file)

    if source is not None:
        session.setdefault(
            "camera_capture_sources", {}
        )[image_file] = source

    linked = False

    for result in session.get("results", []):
        if result.get("scenario_id") == scenario_id:
            result["face_image_file"] = image_file
            result["face_image_files"] = frames.copy()
            linked = True
            break

    _backend().save_sessions()
    return frames, linked












# -------------------- Camera Binding --------------------

@router.post("/api/camera/target")
def set_camera_target(data: ScenarioEvent):
    """Bind incoming live NAO frames to an active scenario."""
    _validate_camera_target(data.session_id, data.scenario_id)

    global _camera_target
    _camera_target = (data.session_id, data.scenario_id)

    return {
        "status": "success",
        "message": "Camera bound to active session/scenario.",
        "session_id": data.session_id,
        "scenario_id": data.scenario_id
    }


@router.delete("/api/camera/target")
def clear_camera_target():
    """Stop linking incoming NAO frames to a session."""
    global _camera_target
    _camera_target = None

    return {
        "status": "success",
        "message": "Camera target cleared."
    }


# -------------------- Standalone Camera Upload --------------------

@router.post("/api/camera/frame")
async def upload_camera_frame(frame: UploadFile = File(...)):
    """Save a standalone validated camera image."""
    ctx = _backend()
    image = await _read_image(frame)

    filename = f"frame_{uuid4().hex}.jpg"
    folder = ctx.ROOT / "data" / "nao_frames"

    relative_path = _save_image(image, folder, filename)

    return {
        "status": "success",
        "message": "Camera frame saved successfully",
        "file_path": relative_path
    }


# -------------------- Live NAO RGB Camera --------------------

def _analyze_nao_camera_frame(session_id, scenario_id, image_file):
    """Run independent facial analysis after the upload response."""
    ctx = _backend()
    session = ctx.sessions.get(session_id)

    if session is None:
        return

    try:
        observation, _ = _run_facial_analysis(
            session, scenario_id, image_file
        )

        status = (
            "Analyzed" if observation is not None
            else "No face detected"
        )

    except Exception as error:
        status = "Analysis failed"
        print("NAO camera facial analysis failed:", repr(error))

    with _facial_lock:
        session.setdefault(
            "camera_analysis_status", {}
        )[image_file] = status

        ctx.save_sessions()


@router.post("/api/camera/raw-frame")
async def upload_raw_camera_frame(
    background_tasks: BackgroundTasks,
    width: int = Form(...),
    height: int = Form(...),
    frame: UploadFile = File(...)
):
    """Receive a raw RGB frame and optionally link it to a session."""
    if (
        width <= 0
        or height <= 0
        or width * height > MAX_RAW_PIXELS
    ):
        raise HTTPException(400, "Invalid camera dimensions.")

    expected_size = width * height * 3
    raw_data = await frame.read(expected_size + 1)

    if len(raw_data) != expected_size:
        raise HTTPException(
            400,
            f"Invalid RGB frame size. Expected {expected_size} "
            f"bytes, received {len(raw_data)}."
        )

    try:
        image = Image.frombytes(
            "RGB", (width, height), raw_data
        )
    except (ValueError, OSError):
        raise HTTPException(400, "Invalid RGB image data.")

    ctx = _backend()
    target = _camera_target

    # Preserve standalone behavior when no target is configured.
    if target is None:
        folder = ctx.ROOT / "data" / "nao_frames"
        filename = f"nao_frame_{uuid4().hex}.jpg"

        image_file = _save_image(image, folder, filename)

        return {
            "status": "success",
            "message": (
                "Unlinked NAO frame saved; bind /api/camera/target "
                "to add frames to a report."
            ),
            "width": width,
            "height": height,
            "file_path": image_file,
            "linked_to_session": False
        }

    session_id, scenario_id = target
    session = _validate_camera_target(session_id, scenario_id)

    folder = (
        ctx.ROOT / "data" / "session_frames" / session_id
    )
    filename = f"scenario_{scenario_id}_{uuid4().hex[:8]}.jpg"

    image_file = _save_image(image, folder, filename)

    frames, _ = _link_frame(
        session,
        scenario_id,
        image_file,
        source="NAO camera (live)"
    )

    session.setdefault(
        "camera_analysis_status", {}
    )[image_file] = "Pending"

    ctx.save_sessions()

    # Return the response without waiting for ResMaskingNet.
    background_tasks.add_task(
        _analyze_nao_camera_frame,
        session_id,
        scenario_id,
        image_file
    )

    return {
        "status": "success",
        "message": "NAO frame linked to the session; analysis queued.",
        "session_id": session_id,
        "scenario_id": scenario_id,
        "image_file": image_file,
        "width": width,
        "height": height,
        "linked_to_session": True,
        "analysis_status": "Pending",
        "total_frames": len(frames)
    }


# -------------------- Session Camera Upload --------------------

@router.post("/api/camera/session-frame")
async def upload_session_frame(
    session_id: str = Form(...),
    scenario_id: int = Form(...),
    frame: UploadFile = File(...)
):
    """Upload and link a validated image to the active scenario."""
    ctx = _backend()
    session = _validate_camera_target(session_id, scenario_id)
    image = await _read_image(frame)

    folder = (
        ctx.ROOT / "data" / "session_frames" / session_id
    )
    filename = f"scenario_{scenario_id}_{uuid4().hex[:8]}.jpg"

    image_file = _save_image(image, folder, filename)

    frames, linked = _link_frame(
        session, scenario_id, image_file
    )

    return {
        "status": "success",
        "session_id": session_id,
        "scenario_id": scenario_id,
        "image_file": image_file,
        "total_frames": len(frames),
        "linked_to_response": linked,
        "message": "Face image saved successfully."
    }


# -------------------- Real Facial Evaluation --------------------

@router.post("/api/facial/evaluate")
def evaluate_facial_frame(data: ScenarioEvent):
    """Run ResMaskingNet without requiring a verbal response."""
    session = _validate_camera_target(
        data.session_id, data.scenario_id
    )

    frames = session.get(
        "captured_frames", {}
    ).get(str(data.scenario_id), [])

    if not frames:
        raise HTTPException(
            404, "No captured facial frame for this scenario."
        )

    image_file = frames[-1]

    try:
        observation, already_evaluated = _run_facial_analysis(
            session, data.scenario_id, image_file
        )
    except FacialInferenceError as error:
        raise HTTPException(
            503, str(error)
        ) from error

    if observation is None:
        raise HTTPException(
            422, "No face was detected in the captured frame."
        )

    result = {
        "status": "success",
        "already_evaluated": already_evaluated,
        "session_id": data.session_id,
        "scenario_id": data.scenario_id,
        "facial_result": observation
    }

    if not already_evaluated:
        result["total_observations"] = len(
            _observations(session, data.scenario_id)
        )

    return result


# -------------------- Mock Facial Results --------------------

@router.post("/api/facial/result")
def save_facial_result(data: FacialResult):
    """Save a mock observation for testing, not real CV statistics."""
    session = _validate_camera_target(
        data.session_id, data.scenario_id
    )

    frames = session.get(
        "captured_frames", {}
    ).get(str(data.scenario_id), [])

    observation = {
        "observation_id": str(uuid4()),
        "dominant_emotion": data.dominant_emotion,
        "confidence": data.confidence,
        "image_file": frames[-1] if frames else None,
        "source": "mock",
        "recorded_at": _now()
    }

    with _facial_lock:
        observations = _observations(
            session, data.scenario_id
        )
        observations.append(observation)
        _backend().save_sessions()
        total = len(observations)

    return {
        "status": "success",
        "session_id": data.session_id,
        "scenario_id": data.scenario_id,
        "facial_result": observation,
        "total_observations": total
    }
