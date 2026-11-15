"""Safely integrate NAO's existing raw-RGB camera upload with session reporting.

Run once from NAO-Emotion-Recognition project root:
    python apply_nao_camera_integration.py

Updates only backend/vision.py and backend/reports.py. Saves *.before_nao_camera.py
backups. Existing Choregraphe behavior.xar and audio/text routes remain untouched.
"""
from pathlib import Path
import re
import shutil
import sys

ROOT = Path.cwd()
VISION = ROOT / "backend" / "vision.py"
REPORTS = ROOT / "backend" / "reports.py"
MARKER = "# NAO_SESSION_CAMERA_INTEGRATION_V1"

HELPERS = '''# NAO_SESSION_CAMERA_INTEGRATION_V1
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


'''

RAW_ROUTE = '''@router.post("/api/camera/raw-frame")
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


'''

REPORT_OBSERVATIONS = '''    emotions = []
    mock_count = 0
    observations = []
    by_image = defaultdict(list)

    def add_observation(scenario_id, observation):
        nonlocal mock_count
        source = observation.get("source")
        if source == "mock":
            mock_count += 1
            return
        if source != "resmaskingnet":
            return
        emotion = observation.get("dominant_emotion")
        if emotion:
            emotions.append(str(emotion))
        record = {
            "scenario_id": scenario_id,
            "observation_id": observation.get("observation_id"),
            "image_file": observation.get("image_file"),
            "dominant_expression": emotion,
            "confidence": observation.get("confidence"),
            "confidence_percent": _confidence_percent(observation.get("confidence")),
            "recorded_at": observation.get("recorded_at"),
            "source": "resmaskingnet",
        }
        observations.append(record)
        if record["image_file"]:
            by_image[(str(scenario_id), str(record["image_file"]))].append(record)

    # Legacy/manual evaluations, previously stored alongside verbal responses.
    for result in results:
        for observation in (result.get("facial_observations") or []):
            add_observation(result.get("scenario_id"), observation)

    # Live NAO observations: independent of whether a verbal answer exists.
    for scenario_id, records in (session.get("facial_observations") or {}).items():
        for observation in (records or []):
            add_observation(scenario_id, observation)

'''


def fail(message):
    raise RuntimeError(message)


def patch_vision(src):
    if MARKER in src:
        fail("vision.py already contains this integration. No files changed.")
    old_import = "from fastapi import APIRouter, File, Form, HTTPException, UploadFile"
    if src.count(old_import) != 1:
        fail("vision.py import changed; please inspect manually before patching.")
    src = src.replace(old_import, "from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile")
    anchor = '@router.post("/api/camera/frame")'
    if src.count(anchor) != 1:
        fail("vision.py camera route marker not found or duplicated.")
    src = src.replace(anchor, HELPERS + anchor)
    pattern = r'@router\.post\("/api/camera/raw-frame"\)\nasync def upload_raw_camera_frame\(.*?(?=\n@router\.post\("/api/camera/session-frame"\))'
    updated, count = re.subn(pattern, RAW_ROUTE, src, count=1, flags=re.S)
    if count != 1:
        fail("vision.py raw-frame route has changed; no files changed.")
    return updated


def patch_reports(src):
    if "# NAO_SESSION_REPORT_INTEGRATION_V1" in src:
        fail("reports.py already contains this integration. No files changed.")
    if '"facial_analysis": {' not in src or 'by_image = defaultdict(list)' not in src:
        fail("Expected enhanced reports.py is not installed. Install the separated report first.")
    # Start within generate_session_report only: don't touch earlier frame helper.
    function_start = src.find('def generate_session_report(')
    if function_start < 0:
        fail("reports.py report generator not found.")
    observations_start = src.find('    emotions = []\n', function_start)
    observations_end = src.find('    frames = []\n', observations_start)
    if observations_start < 0 or observations_end < 0:
        fail("reports.py facial observation block not found.")
    src = src[:observations_start] + REPORT_OBSERVATIONS + src[observations_end:]

    old_status = '"analysis_status": "Analyzed" if last else "Not analyzed",'
    new_status = ('"analysis_status": "Analyzed" if last else '
                  '(session.get("camera_analysis_status") or {}).get(path, "Not analyzed"),\n'
                  '                "capture_source": (session.get("camera_capture_sources") or {}).get(\n'
                  '                    path, "Source not verified"\n'
                  '                ),')
    if src.count(old_status) != 1:
        fail("reports.py frame status line not found.")
    src = src.replace(old_status, new_status)
    old_label = '            <div class="muted">Model observation: {label}</div>'
    new_label = ('            <div class="muted">Capture source: {safe(frame[\'capture_source\'])}</div>\n'
                 '            <div class="muted">Model observation: {label}</div>')
    if src.count(old_label) != 1:
        fail("reports.py HTML image metadata marker not found.")
    src = src.replace(old_label, new_label)
    # Distinguish Pending/no-face/error from a generic not-analyzed frame.
    src = src.replace('else "Not analyzed"\n        )\n        frame_cards',
                      'else safe(frame["analysis_status"])\n        )\n        frame_cards')
    return '# NAO_SESSION_REPORT_INTEGRATION_V1\n' + src


def main():
    if not VISION.is_file() or not REPORTS.is_file():
        fail("Run from the NAO-Emotion-Recognition root containing backend/vision.py.")
    vision_src = VISION.read_text(encoding="utf-8")
    report_src = REPORTS.read_text(encoding="utf-8")
    vision_updated = patch_vision(vision_src)
    report_updated = patch_reports(report_src)
    # Check syntax of both updated files before making any changes.
    compile(vision_updated, str(VISION), "exec")
    compile(report_updated, str(REPORTS), "exec")
    for path in (VISION, REPORTS):
        backup = path.with_name(path.name + ".before_nao_camera")
        if backup.exists():
            fail(f"Backup already exists: {backup}. No files changed.")
    shutil.copy2(VISION, VISION.with_name(VISION.name + ".before_nao_camera"))
    shutil.copy2(REPORTS, REPORTS.with_name(REPORTS.name + ".before_nao_camera"))
    try:
        VISION.write_text(vision_updated, encoding="utf-8")
        REPORTS.write_text(report_updated, encoding="utf-8")
    except Exception:
        shutil.copy2(VISION.with_name(VISION.name + ".before_nao_camera"), VISION)
        shutil.copy2(REPORTS.with_name(REPORTS.name + ".before_nao_camera"), REPORTS)
        raise
    print("SUCCESS: backend/vision.py and backend/reports.py updated.")
    print("Backups: *.py.before_nao_camera")
    print("NAO's existing Choregraphe behavior.xar was NOT modified.")
    print("New camera binding API: POST /api/camera/target; DELETE /api/camera/target")
    print("Incoming raw-frame captures are analyzed independently of spoken answers.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.exit(f"PATCH FAILED: {exc}")
