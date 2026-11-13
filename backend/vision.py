"""NAO camera API: image acquisition, frame storage, facial inference and results.

The ResMaskingNet inference adapter is backend.facial_classifier. The shared
sessions/reporting logic stays in backend.app. No model weights are loaded
while importing this module.
"""

import os
from datetime import datetime, timezone
import backend
from io import BytesIO
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image

from backend.facial_classifier import FacialInferenceError, classify_facial_frame
from backend.schemas import ScenarioEvent, FacialResult

router = APIRouter(tags=["Camera / Computer Vision"])


def _backend():
    """Access shared session state lazily; avoids import cycles."""
    # Use the already loaded package module (no recursive re-import).
    # This also preserves monkeypatched backend.app aliases in offline tests.
    return backend.app


@router.post("/api/camera/frame")
async def upload_camera_frame(frame: UploadFile = File(...)):
    """Store a standalone uploaded camera frame in data/nao_frames.
    
    This lightweight/legacy endpoint does not associate an image with a
    specific training session."""
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
    width: int = Form(...),
    height: int = Form(...),
    frame: UploadFile = File(...)
):
    """Convert raw RGB bytes from NAO to a local JPEG image.
    
    width * height * 3 must match the byte count because every RGB pixel
    contains three color channels. This is not a model inference endpoint."""
    folder = "data/nao_frames"
    os.makedirs(folder, exist_ok=True)

    raw_data = await frame.read()

    expected_size = width * height * 3

    if len(raw_data) != expected_size:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid RGB frame size. "
                f"Expected {expected_size} bytes, "
                f"received {len(raw_data)}."
            )
        )

    image = Image.frombytes(
        "RGB",
        (width, height),
        raw_data
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"nao_frame_{timestamp}.jpg"
    file_path = os.path.join(folder, filename)

    image.save(
        file_path,
        format="JPEG",
        quality=90
    )

    return {
        "status": "success",
        "message": "NAO camera frame received and saved successfully",
        "width": width,
        "height": height,
        "file_path": file_path
    }


@router.post("/api/camera/session-frame")
async def upload_session_frame(
    session_id: str = Form(...),
    scenario_id: int = Form(...),
    frame: UploadFile = File(...)
):
    """Validate and save an image for one active session and scenario.
    
    Frames are accepted before or after the corresponding verbal response.
    When an answer is already saved, its image references are updated."""
    ctx = _backend()
    sessions = ctx.sessions
    scenarios_db = ctx.scenarios_db
    ROOT = ctx.ROOT
    save_sessions = ctx.save_sessions

    # Step 1: Validate the session.
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

    # Step 2: Validate the scenario independently of the verbal response.
    if not any(
        item["scenario_id"] == scenario_id
        for item in scenarios_db
    ):
        raise HTTPException(
            status_code=404,
            detail="Scenario not found."
        )

    # STEP 3 - Validate the uploaded image before saving it to disk.
    # Byte and pixel limits protect against oversized/unreadable input.
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

    # Step 4: Save the image.
    image_folder = (
        ROOT / "data" / "session_frames" / session_id
    )
    image_folder.mkdir(parents=True, exist_ok=True)

    filename = f"scenario_{scenario_id}_{uuid4().hex[:8]}.jpg"
    image_path = image_folder / filename

    image.save(image_path, format="JPEG", quality=90)

    # STEP 5 - Track frames immediately: the audio response can arrive later.
    relative_path = image_path.relative_to(ROOT).as_posix()
    captured_frames = session.setdefault("captured_frames", {})
    frames = captured_frames.setdefault(str(scenario_id), [])
    frames.append(relative_path)

    # If the response already exists, link all captured frames to it.
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
    """Run ResMaskingNet on the latest frame in the active scenario.

    This route creates a real model observation; /api/facial/result remains a
    separate mock-only endpoint for tests and manual prototype demonstrations.
    """
    ctx = _backend()
    sessions = ctx.sessions
    ROOT = ctx.ROOT
    save_sessions = ctx.save_sessions
    classify_facial_frame = ctx.classify_facial_frame

    session = sessions.get(data.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.get("status") != "active":
        raise HTTPException(status_code=409, detail="Session has already ended.")
    if session.get("active_scenario_id") != data.scenario_id:
        raise HTTPException(
            status_code=409,
            detail="Start the requested scenario before facial evaluation."
        )

    result = next(
        (item for item in session["results"]
         if item["scenario_id"] == data.scenario_id),
        None
    )
    if result is None:
        raise HTTPException(
            status_code=409,
            detail="Submit the verbal response before facial evaluation."
        )

    frames = session.get("captured_frames", {}).get(str(data.scenario_id), [])
    if not frames:
        raise HTTPException(
            status_code=404,
            detail="No captured facial frame for this scenario."
        )

    image_file = frames[-1]
    # Avoid charging the same exact frame twice to the session/report.
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
        raise HTTPException(status_code=400, detail="Invalid stored frame path.")
    if not image_path.is_file():
        raise HTTPException(status_code=404, detail="Stored frame not found.")

    try:
        prediction = classify_facial_frame(image_path)
    except FacialInferenceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    # A missing face is NOT an emotion result; avoid storing a false reading.
    if prediction is None:
        raise HTTPException(
            status_code=422,
            detail="No face was detected in the captured frame."
        )

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
    """Store a manually provided/mock facial result for prototype tests.
    
    Observations saved here are deliberately marked source='mock' so the
    report can exclude them from real ResMaskingNet statistics."""

    ctx = _backend()
    sessions = ctx.sessions
    save_sessions = ctx.save_sessions

    # Verify session
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

    # Find the matching scenario response
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

    # This is the mock-only endpoint; real model inference has its own route.
    # Store a facial observation
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

    # Support multiple observations per scenario
    result.setdefault(
        "facial_observations", []
    ).append(observation)

    # Save session permanently
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
