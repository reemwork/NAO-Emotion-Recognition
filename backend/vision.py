
# Handles NAO camera images and facial expression results.
import os
from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from PIL import Image

import backend
from backend.facial_classifier import FacialInferenceError, classify_facial_frame
from backend.schemas import FacialResult, ScenarioEvent


router = APIRouter(tags=["Camera / Computer Vision"])


def _backend():
    return backend.app


# NAO_SESSION_CAMERA_INTEGRATION_V1
# The PC binds a single active session/scenario; the existing NAO camera box
# can continue POSTing width, height and raw RGB to /api/camera/raw-frame.
# No session is inferred from filenames or from "the most recent" session.
_camera_target = None


def _validate_camera_target(session_id, scenario_id):
    ctx = _backend()
    session = ctx.sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.get("status") != "active":
        raise HTTPException(status_code=409, detail="Session is not active.")
    if session.get("active_scenario_id") != scenario_id:
        raise HTTPException(
            status_code=409,
            detail="Camera target does not match the active scenario. Rebind the camera."
        )
    if not any(item.get("scenario_id") == scenario_id for item in ctx.scenarios_db):
        raise HTTPException(status_code=404, detail="Scenario not found.")
    return session


@router.post("/api/camera/target")
def set_camera_target(data: ScenarioEvent):
    """Explicitly select the active scenario for incoming NAO camera frames."""
    _validate_camera_target(data.session_id, data.scenario_id)
    global _camera_target
    _camera_target = (data.session_id, data.scenario_id)
    return {
        "status": "success",
        "message": "Camera bound to active session/scenario.",
        "session_id": data.session_id,
        "scenario_id": data.scenario_id,
    }


@router.delete("/api/camera/target")
def clear_camera_target():
    """Stop attaching incoming NAO frames to a session."""
    global _camera_target
    _camera_target = None
    return {"status": "success", "message": "Camera target cleared."}


def _analyze_nao_camera_frame(session_id, scenario_id, image_file):
    """Analyze AFTER replying to NAO; no verbal response is required."""
    ctx = _backend()
    session = ctx.sessions.get(session_id)
    if session is None:
        return

    status = "Analyzed"
    prediction = None
    try:
        prediction = ctx.classify_facial_frame(ctx.ROOT / image_file)
        if prediction is None:
            status = "No face detected"
    except Exception as exc:
        # Frame remains in the report even when a model cannot evaluate it.
        status = "Analysis failed"
        print("NAO camera facial analysis failed:", repr(exc))

    session.setdefault("camera_analysis_status", {})[image_file] = status
    if prediction is not None:
        observation = {
            "observation_id": str(uuid4()),
            "dominant_emotion": prediction["dominant_emotion"],
            "confidence": prediction["confidence"],
            "image_file": image_file,
            "source": "resmaskingnet",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        # Independent of the verbal answer: can exist before /response/submit.
        session.setdefault("facial_observations", {}).setdefault(
            str(scenario_id), []
        ).append(observation)
    ctx.save_sessions()


@router.post("/api/camera/frame")
async def upload_camera_frame(frame: UploadFile = File(...)):
    # Save an image without linking it to a session.
    folder = "data/nao_frames"
    os.makedirs(folder, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    extension = os.path.splitext(frame.filename)[1].lower()

    if not extension:
        extension = ".jpg"

    filename = f"frame_{timestamp}{extension}"
    file_path = os.path.join(folder, filename)

    contents = await frame.read()

    with open(file_path, "wb") as f:
        f.write(contents)

    return {
        "status": "success",
        "message": "Camera frame saved successfully",
        "file_path": file_path
    }


@router.post("/api/camera/raw-frame")
async def upload_raw_camera_frame(
    background_tasks: BackgroundTasks,
    width: int = Form(...),
    height: int = Form(...),
    frame: UploadFile = File(...)
):
    """Receive NAO RGB frame; link and analyze if an explicit camera target exists."""
    if width <= 0 or height <= 0 or width * height > 3_000_000:
        raise HTTPException(status_code=400, detail="Invalid camera dimensions.")

    raw_data = await frame.read()
    expected_size = width * height * 3
    if len(raw_data) != expected_size:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid RGB frame size. Expected {expected_size} bytes, "
                   f"received {len(raw_data)}."
        )

    try:
        image = Image.frombytes("RGB", (width, height), raw_data)
    except (ValueError, OSError):
        raise HTTPException(status_code=400, detail="Invalid RGB image data.")

    target = _camera_target
    if target is None:
        # Preserve the old endpoint for development/testing when no target is set.
        folder = _backend().ROOT / "data" / "nao_frames"
        folder.mkdir(parents=True, exist_ok=True)
        filename = f"nao_frame_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
        file_path = folder / filename
        image.save(file_path, format="JPEG", quality=90)
        return {
            "status": "success",
            "message": "Unlinked NAO frame saved; bind /api/camera/target to add frames to a report.",
            "width": width, "height": height,
            "file_path": file_path.relative_to(_backend().ROOT).as_posix(),
            "linked_to_session": False,
        }

    session_id, scenario_id = target
    session = _validate_camera_target(session_id, scenario_id)
    ctx = _backend()
    image_folder = ctx.ROOT / "data" / "session_frames" / session_id
    image_folder.mkdir(parents=True, exist_ok=True)
    image_path = image_folder / f"scenario_{scenario_id}_{uuid4().hex[:8]}.jpg"
    image.save(image_path, format="JPEG", quality=90)
    relative_path = image_path.relative_to(ctx.ROOT).as_posix()

    frames = session.setdefault("captured_frames", {}).setdefault(str(scenario_id), [])
    frames.append(relative_path)
    session.setdefault("camera_capture_sources", {})[relative_path] = "NAO camera (live)"
    session.setdefault("camera_analysis_status", {})[relative_path] = "Pending"

    # Preserve the existing response's frame links if that response exists.
    for result in session.get("results", []):
        if result.get("scenario_id") == scenario_id:
            result["face_image_file"] = relative_path
            result["face_image_files"] = frames.copy()
            break

    ctx.save_sessions()
    # Returning to NAO immediately avoids a robot-side 10s timeout while
    # ResMaskingNet is still loading/running on the external computer.
    background_tasks.add_task(
        _analyze_nao_camera_frame, session_id, scenario_id, relative_path
    )
    return {
        "status": "success",
        "message": "NAO frame linked to the session; analysis queued.",
        "session_id": session_id, "scenario_id": scenario_id,
        "image_file": relative_path, "width": width, "height": height,
        "linked_to_session": True,
        "analysis_status": "Pending",
        "total_frames": len(frames),
    }



@router.post("/api/camera/session-frame")
async def upload_session_frame(
    session_id: str = Form(...),
    scenario_id: int = Form(...),
    frame: UploadFile = File(...)
):
    ctx = _backend()
    sessions = ctx.sessions
    scenarios_db = ctx.scenarios_db
    ROOT = ctx.ROOT
    save_sessions = ctx.save_sessions

    # Check that the session is active.
    session = sessions.get(session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    if session.get("status") != "active":
        raise HTTPException(
            status_code=409,
            detail="Session has already ended."
        )

    # Check that the scenario exists.
    if not any(
        item["scenario_id"] == scenario_id
        for item in scenarios_db
    ):
        raise HTTPException(
            status_code=404,
            detail="Scenario not found."
        )

    # Check the image before saving it.
    contents = await frame.read()

    if not contents or len(contents) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="Image must be non-empty and at most 10 MB."
        )

    try:
        with Image.open(BytesIO(contents)) as uploaded:
            if uploaded.width * uploaded.height > 20_000_000:
                raise ValueError("Image dimensions are too large.")

            image = uploaded.convert("RGB")

    except (OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(
            status_code=400,
            detail="Invalid image file."
        )

    # Save the image in its session folder.
    image_folder = (
        ROOT / "data" / "session_frames" / session_id
    )
    image_folder.mkdir(parents=True, exist_ok=True)

    filename = f"scenario_{scenario_id}_{uuid4().hex[:8]}.jpg"
    image_path = image_folder / filename

    image.save(image_path, format="JPEG", quality=90)

    # Link the image to its scenario.
    relative_path = image_path.relative_to(ROOT).as_posix()
    captured_frames = session.setdefault("captured_frames", {})
    frames = captured_frames.setdefault(str(scenario_id), [])
    frames.append(relative_path)

    # Update the response if it was already submitted.
    result = next(
        (
            item for item in session["results"]
            if item["scenario_id"] == scenario_id
        ),
        None
    )

    if result is not None:
        result["face_image_file"] = relative_path
        result["face_image_files"] = frames.copy()

    save_sessions()

    return {
        "status": "success",
        "session_id": session_id,
        "scenario_id": scenario_id,
        "image_file": relative_path,
        "total_frames": len(frames),
        "linked_to_response": result is not None,
        "message": "Face image saved successfully."
    }


@router.post("/api/facial/evaluate")
def evaluate_facial_frame(data: ScenarioEvent):
    ctx = _backend()
    sessions = ctx.sessions
    ROOT = ctx.ROOT
    save_sessions = ctx.save_sessions
    classify_facial_frame = ctx.classify_facial_frame

    # Check the session and active scenario.
    session = sessions.get(data.session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    if session.get("status") != "active":
        raise HTTPException(
            status_code=409,
            detail="Session has already ended."
        )

    if session.get("active_scenario_id") != data.scenario_id:
        raise HTTPException(
            status_code=409,
            detail="Start the requested scenario before facial evaluation."
        )

    # Find the saved verbal response.
    result = next(
        (
            item for item in session["results"]
            if item["scenario_id"] == data.scenario_id
        ),
        None
    )

    if result is None:
        raise HTTPException(
            status_code=409,
            detail="Submit the verbal response before facial evaluation."
        )

    # Get the latest image from this scenario.
    frames = session.get("captured_frames", {}).get(
        str(data.scenario_id), []
    )

    if not frames:
        raise HTTPException(
            status_code=404,
            detail="No captured facial frame for this scenario."
        )

    image_file = frames[-1]

    # Avoid analyzing the same image twice.
    for observation in result.get("facial_observations", []):
        if (
            observation.get("source") == "resmaskingnet"
            and observation.get("image_file") == image_file
        ):
            return {
                "status": "success",
                "already_evaluated": True,
                "session_id": data.session_id,
                "scenario_id": data.scenario_id,
                "facial_result": observation
            }

    image_path = (ROOT / image_file).resolve()

    if not image_path.is_relative_to(ROOT.resolve()):
        raise HTTPException(
            status_code=400,
            detail="Invalid stored frame path."
        )

    if not image_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Stored frame not found."
        )

    # Analyze the image using the facial emotion model.
    try:
        prediction = classify_facial_frame(image_path)

    except FacialInferenceError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error)
        ) from error

    if prediction is None:
        raise HTTPException(
            status_code=422,
            detail="No face was detected in the captured frame."
        )

    # Save the predicted emotion and confidence.
    observation = {
        "observation_id": str(uuid4()),
        "dominant_emotion": prediction["dominant_emotion"],
        "confidence": prediction["confidence"],
        "image_file": image_file,
        "source": "resmaskingnet",
        "recorded_at": datetime.now(timezone.utc).isoformat()
    }

    result.setdefault("facial_observations", []).append(observation)
    save_sessions()

    return {
        "status": "success",
        "already_evaluated": False,
        "session_id": data.session_id,
        "scenario_id": data.scenario_id,
        "facial_result": observation,
        "total_observations": len(result["facial_observations"])
    }


@router.post("/api/facial/result")
def save_facial_result(data: FacialResult):
    ctx = _backend()
    sessions = ctx.sessions
    save_sessions = ctx.save_sessions

    session = sessions.get(data.session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    if session.get("status") != "active":
        raise HTTPException(
            status_code=409,
            detail="Session has already ended."
        )

    # Find the response linked to this scenario.
    result = next(
        (
            item for item in session["results"]
            if item["scenario_id"] == data.scenario_id
        ),
        None
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No saved response for this scenario."
        )

    # Save test results without running the facial model.
    observation = {
        "observation_id": str(uuid4()),
        "dominant_emotion": data.dominant_emotion,
        "confidence": data.confidence,
        "image_file": result.get("face_image_file"),
        "source": "mock",
        "recorded_at": datetime.now(
            timezone.utc
        ).isoformat()
    }

    result.setdefault(
        "facial_observations", []
    ).append(observation)

    save_sessions()

    return {
        "status": "success",
        "session_id": data.session_id,
        "scenario_id": data.scenario_id,
        "facial_result": observation,
        "total_observations": len(
            result["facial_observations"]
        )
    }
