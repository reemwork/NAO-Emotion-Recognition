import glob
import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Literal
from uuid import uuid4

import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from PIL import Image
from pydantic import BaseModel, Field

from backend.emotion_classifier import classify_emotion
from backend.transcribe_audio import model as whisper_model
from backend.transcribe_audio import transcribe_audio

app = FastAPI(
    title="NAO Emotion Training Backend",
    version="1.0"
)



ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_FILE = ROOT / "data" / "scenarios.json"

with open(SCENARIOS_FILE, "r", encoding="utf-8") as file:
    scenarios_db = json.load(file)
SESSIONS_FILE = ROOT / "data" / "sessions.json"


def load_sessions():
    if not SESSIONS_FILE.exists():
        return {}

    with open(SESSIONS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


sessions = load_sessions()


def save_sessions():
    SESSIONS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_file = SESSIONS_FILE.with_suffix(".json.tmp")

    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(
            sessions,
            file,
            indent=4,
            ensure_ascii=False
        )

    temp_file.replace(SESSIONS_FILE)

class ChildResponse(BaseModel):
    session_id: str
    scenario_id: int
    spoken_text: str


class ScenarioEvent(BaseModel):
    session_id: str
    scenario_id: int


class SessionEnd(BaseModel):
    session_id: str


class FacialResult(BaseModel):
    session_id: str
    scenario_id: int
    dominant_emotion: Literal[
        "Happy", "Sad", "Angry", "Neutral",
        "Fear", "Surprise", "Disgust"
    ]
    confidence: float = Field(ge=0, le=1)

@app.get("/")
def read_root():
    return {
        "status": "online"
    }



@app.post("/api/session/start")
def start_session():
    session_id = str(uuid4())

    sessions[session_id] = {
        "session_id": session_id,
        "status": "active",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "active_scenario_id": None,
        "scenario_progress": {},
        "results": []
    }
    save_sessions()
    return {
        "status": "success",
        "session_id": session_id,
        "total_scenarios": len(scenarios_db)
    }


@app.post("/api/session/end")
def end_session(data: SessionEnd):
    session = sessions.get(data.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    # Repeated requests are safe and keep the original completion time.
    if session.get("status") != "active":
        return {
            "status": "success",
            "session_id": data.session_id,
            "session_status": session["status"],
            "ended_at": session.get("ended_at"),
            "completed_scenarios": sum(
                state.get("status") == "completed"
                for state in session.get("scenario_progress", {}).values()
            ),
            "total_scenarios": len(scenarios_db),
            "already_ended": True
        }

    if session.get("active_scenario_id") is not None:
        raise HTTPException(
            status_code=409,
            detail="Complete the active scenario before ending the session."
        )

    progress = session.get("scenario_progress", {})
    completed_count = sum(
        progress.get(str(scenario["scenario_id"]), {}).get("status")
        == "completed"
        for scenario in scenarios_db
    )
    finished_all = completed_count == len(scenarios_db)

    session["status"] = "completed" if finished_all else "ended_early"
    session["ended_at"] = datetime.now(timezone.utc).isoformat()
    save_sessions()

    return {
        "status": "success",
        "session_id": data.session_id,
        "session_status": session["status"],
        "ended_at": session["ended_at"],
        "completed_scenarios": completed_count,
        "total_scenarios": len(scenarios_db),
        "already_ended": False
    }


@app.get("/api/scenario/next")
def get_next_scenario(index: int = 0):
    if index < len(scenarios_db):
        return {
            "status": "success",
            "has_more": True,
            "scenario": scenarios_db[index]
        }

    return {
        "status": "success",
        "has_more": False,
        "message": "All scenarios completed."
    }




@app.post("/api/scenario/start")
def start_scenario(data: ScenarioEvent):
    session = sessions.get(data.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    if session.get("status") != "active":
        raise HTTPException(status_code=409, detail="Session is not active.")

    if not any(
        scenario["scenario_id"] == data.scenario_id
        for scenario in scenarios_db
    ):
        raise HTTPException(status_code=404, detail="Scenario not found.")

    active_id = session.get("active_scenario_id")
    if active_id is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Scenario {active_id} is already in progress."
        )

    progress = session.setdefault("scenario_progress", {})
    key = str(data.scenario_id)
    if key in progress or any(
        result["scenario_id"] == data.scenario_id
        for result in session["results"]
    ):
        raise HTTPException(
            status_code=409,
            detail="This scenario was already started or evaluated."
        )

    started_at = datetime.now(timezone.utc).isoformat()
    progress[key] = {
        "status": "in_progress",
        "started_at": started_at,
        "completed_at": None
    }
    session["active_scenario_id"] = data.scenario_id
    save_sessions()

    return {
        "status": "success",
        "session_id": data.session_id,
        "scenario_id": data.scenario_id,
        "scenario_status": "in_progress",
        "started_at": started_at
    }


@app.post("/api/scenario/complete")
def complete_scenario(data: ScenarioEvent):
    session = sessions.get(data.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    if not any(
        scenario["scenario_id"] == data.scenario_id
        for scenario in scenarios_db
    ):
        raise HTTPException(status_code=404, detail="Scenario not found.")

    progress = session.get("scenario_progress", {})
    state = progress.get(str(data.scenario_id))
    if (
        state is None
        or state.get("status") != "in_progress"
        or session.get("active_scenario_id") != data.scenario_id
    ):
        raise HTTPException(
            status_code=409,
            detail="This scenario is not currently in progress."
        )

    # Complete only after a verbal response has been saved.
    # Handling missing/failed audio will be added separately.
    if not any(
        result["scenario_id"] == data.scenario_id
        for result in session["results"]
    ):
        raise HTTPException(
            status_code=409,
            detail="Cannot complete a scenario without a saved verbal response."
        )

    completed_at = datetime.now(timezone.utc).isoformat()
    state["status"] = "completed"
    state["completed_at"] = completed_at
    session["active_scenario_id"] = None
    save_sessions()

    return {
        "status": "success",
        "session_id": data.session_id,
        "scenario_id": data.scenario_id,
        "scenario_status": "completed",
        "started_at": state["started_at"],
        "completed_at": completed_at
    }


@app.post("/api/response/submit")

@app.post("/api/response/submit")
def submit_response(data: ChildResponse):

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

    scenario = next(
        (
            item for item in scenarios_db
            if item["scenario_id"] == data.scenario_id
        ),
        None
    )

    if scenario is None:
        raise HTTPException(
            status_code=404,
            detail="Scenario not found."
        )

    spoken_text = data.spoken_text.strip()

    if not spoken_text:
        raise HTTPException(
            status_code=400,
            detail="Response cannot be empty."
        )

    if any(
        result["scenario_id"] == data.scenario_id
        for result in session["results"]
    ):
        raise HTTPException(
            status_code=409,
            detail="Response already submitted for this scenario."
        )

    # Step 1: Classify the verbal response using Qwen
    try:
        predicted_emotion = classify_emotion(spoken_text)

    except (requests.RequestException, RuntimeError) as error:
        print("MLLM classification failed:", error)
        raise HTTPException(
            status_code=503,
            detail="Emotion classification is unavailable."
        )

    # Step 2: Compare prediction with the reference label
    reference_label = scenario["reference_label"]

    if predicted_emotion == "Unclear":
        evaluation = "Unclear"

    elif predicted_emotion == reference_label:
        evaluation = "Correct"

    else:
        evaluation = "Incorrect"

    # Step 3: Save the result in the current session
    result = {
        "scenario_id": data.scenario_id,
        "reference_label": reference_label,
        "spoken_text": spoken_text,
        "predicted_emotion": predicted_emotion,
        "evaluation": evaluation
    }

    # Attach images captured before the verbal answer was submitted.
    frames = session.get("captured_frames", {}).get(
        str(data.scenario_id), []
    )
    if frames:
        result["face_image_file"] = frames[-1]
        result["face_image_files"] = frames.copy()

    session["results"].append(result)
    save_sessions()

    return {
        "status": "success",
        "session_id": data.session_id,
        "saved_result": result,
        "total_responses": len(session["results"])
    }

@app.post("/api/camera/frame")
async def upload_camera_frame(frame: UploadFile = File(...)):
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


@app.post("/api/camera/raw-frame")
async def upload_raw_camera_frame(
    width: int = Form(...),
    height: int = Form(...),
    frame: UploadFile = File(...)
):
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

#Nada's
@app.post("/api/audio/upload")
async def upload_nao_audio(audio: UploadFile = File(...)):
    folder = "data/nao_audio"
    os.makedirs(folder, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    audio_filename = f"response_{timestamp}.wav"
    audio_file_path = os.path.join(folder, audio_filename)

    contents = await audio.read()

    with open(audio_file_path, "wb") as f:
        f.write(contents)

    transcript = transcribe_audio(audio_file_path)

    text_filename = f"response_{timestamp}.txt"
    text_file_path = os.path.join(folder, text_filename)

    with open(text_file_path, "w", encoding="utf-8") as f:
        f.write(transcript)

    return {
        "status": "success",
        "message": "NAO audio saved and transcribed successfully",
        "audio_file": audio_file_path,
        "text_file": text_file_path,
        "transcript": transcript
    }

@app.post("/api/audio/capture")
def capture_nao_audio():
    nao_ip = "169.254.247.199"
    remote_audio = "/home/nao/recordings/microphones/response.wav"

    folder = "data/nao_audio"
    os.makedirs(folder, exist_ok=True)

    audio_files = glob.glob(
        os.path.join(folder, "response_*.wav")
    )

    numbers = []

    for file in audio_files:
        filename = os.path.basename(file)

        match = re.fullmatch(
            r"response_(\d+)\.wav",
            filename
        )

        if match:
            numbers.append(int(match.group(1)))

    next_number = max(numbers, default=0) + 1

    audio_filename = f"response_{next_number}.wav"
    audio_file_path = os.path.join(folder, audio_filename)

    try:
        subprocess.run(
            [
                "scp",
                f"nao@{nao_ip}:{remote_audio}",
                audio_file_path
            ],
            check=True
        )

    except subprocess.CalledProcessError:
        raise HTTPException(
            status_code=500,
            detail="Failed to download audio from NAO."
        )

    return {
        "status": "success",
        "message": "NAO audio downloaded successfully",
        "audio_file": audio_file_path
    }


@app.get("/api/session/{session_id}")
def get_session_results(session_id: str):

    session = sessions.get(session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    results = session["results"]

    summary = {
        "correct": sum(
            r["evaluation"] == "Correct"
            for r in results
        ),
        "incorrect": sum(
            r["evaluation"] == "Incorrect"
            for r in results
        ),
        "unclear": sum(
            r["evaluation"] == "Unclear"
            for r in results
        )
    }

    return {
        "status": "success",
        "session_id": session_id,
        "total_scenarios": len(scenarios_db),
        "total_responses": len(results),
        "session_status": session.get("status", "active"),
        "session_started_at": session.get("started_at"),
        "session_ended_at": session.get("ended_at"),
        "active_scenario_id": session.get("active_scenario_id"),
        "scenario_progress": session.get("scenario_progress", {}),
        "captured_frames": session.get("captured_frames", {}),
        "results": results,
        "summary": summary
    }


@app.post("/api/audio/evaluate")
def evaluate_audio(
    session_id: str = Form(...),
    scenario_id: int = Form(...),
    audio: UploadFile = File(...)
):
    # Verify that the session exists.
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

    # Verify that the scenario exists.
    if not any(
        item["scenario_id"] == scenario_id
        for item in scenarios_db
    ):
        raise HTTPException(
            status_code=404,
            detail="Scenario not found."
        )

    # Prevent duplicate submissions.
    if any(
        result["scenario_id"] == scenario_id
        for result in session["results"]
    ):
        raise HTTPException(
            status_code=409,
            detail="Response already submitted for this scenario."
        )

    # Accept WAV recordings only.
    if not (audio.filename or "").lower().endswith(".wav"):
        raise HTTPException(
            status_code=400,
            detail="Only WAV audio files are supported."
        )

    # Read and validate uploaded audio.
    audio_data = audio.file.read()

    if not audio_data or len(audio_data) > 20 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="Audio must be non-empty and at most 20 MB."
        )

    # Save audio under the current session.
    audio_folder = (
        ROOT / "data" / "session_audio" / session_id
    )

    audio_folder.mkdir(parents=True, exist_ok=True)

    audio_filename = (
        f"scenario_{scenario_id}_{uuid4().hex[:8]}.wav"
    )

    audio_path = audio_folder / audio_filename
    audio_path.write_bytes(audio_data)

    # Step 1: Speech-to-text using Whisper.
    try:
        whisper_result = whisper_model.transcribe(
            str(audio_path),
            language="en",
            fp16=False
        )

        transcript = whisper_result["text"].strip()

    except Exception as error:
        audio_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=500,
            detail="Audio transcription failed."
        ) from error

    if not transcript:
        audio_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=422,
            detail="No speech was recognized."
        )

    # Step 2: Reuse the existing Qwen evaluation.
    try:
        response = submit_response(
            ChildResponse(
                session_id=session_id,
                scenario_id=scenario_id,
                spoken_text=transcript
            )
        )

    except HTTPException:
        audio_path.unlink(missing_ok=True)
        raise

    # Step 3: Link audio to the saved result.
    relative_audio_path = audio_path.relative_to(ROOT)

    response["saved_result"]["audio_file"] = (
        relative_audio_path.as_posix()
    )

    save_sessions()

    return response

@app.post("/api/camera/session-frame")
async def upload_session_frame(
    session_id: str = Form(...),
    scenario_id: int = Form(...),
    frame: UploadFile = File(...)
):
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

    # Step 3: Read and validate the image.
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

    # Step 5: Store frames even when audio has not arrived yet.
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


@app.post("/api/facial/result")
def save_facial_result(data: FacialResult):

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


@app.get("/api/session/{session_id}/report")
def generate_session_report(session_id: str):

    session = sessions.get(session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    results = session["results"]

    correct = sum(
        r.get("evaluation") == "Correct"
        for r in results
    )

    incorrect = sum(
        r.get("evaluation") == "Incorrect"
        for r in results
    )

    unclear = sum(
        r.get("evaluation") == "Unclear"
        for r in results
    )

    evaluated = correct + incorrect

    accuracy = (
        round(correct / evaluated * 100, 2)
        if evaluated > 0 else None
    )

    facial_emotions = []
    mock_count = 0
    scenario_reports = []

    for result in results:

        observations = result.get(
            "facial_observations", []
        )

        real_observations = []

        for obs in observations:
            if obs.get("source") == "mock":
                mock_count += 1

            elif obs.get("source") == "resmaskingnet":
                real_observations.append(obs)
                facial_emotions.append(
                    obs["dominant_emotion"]
                )

        verbal_emotion = result.get(
            "predicted_emotion"
        )

        if real_observations:

            dominant_facial = Counter(
                obs["dominant_emotion"]
                for obs in real_observations
            ).most_common(1)[0][0]

            if verbal_emotion == "Unclear":
                comparison = "Unavailable"

            elif verbal_emotion == dominant_facial:
                comparison = "Agreement"

            else:
                comparison = "Mismatch"

        else:
            dominant_facial = None
            comparison = "Unavailable"

        scenario_reports.append({
            "scenario_id": result["scenario_id"],
            "reference_label": result["reference_label"],
            "spoken_text": result["spoken_text"],
            "verbal_emotion": verbal_emotion,
            "answer_evaluation": result["evaluation"],
            "dominant_facial_expression": dominant_facial,
            "verbal_facial_comparison": comparison
        })

    most_frequent_facial = (
        Counter(facial_emotions).most_common(1)[0][0]
        if facial_emotions else None
    )

    return {
        "session_id": session_id,
        "report_type": "Technical Prototype Report",
        "total_scenarios": len(scenarios_db),
        "completed_scenarios": len(results),
        "verbal_performance": {
            "correct": correct,
            "incorrect": incorrect,
            "unclear": unclear,
            "accuracy_excluding_unclear": accuracy
        },
        "facial_analysis": {
            "model_observations": len(facial_emotions),
            "mock_observations_excluded": mock_count,
            "most_frequent_expression": most_frequent_facial
        },
        "scenario_details": scenario_reports
    }

@app.get(
    "/api/session/{session_id}/report/view",
    response_class=HTMLResponse
)
def view_session_report(session_id: str):

    report = generate_session_report(session_id)

    performance = report["verbal_performance"]
    facial = report["facial_analysis"]

    accuracy = performance["accuracy_excluding_unclear"]
    accuracy_text = (
        f"{accuracy}%"
        if accuracy is not None
        else "N/A"
    )

    rows = ""

    for item in report["scenario_details"]:
        rows += f"""
        <tr>
            <td>{item['scenario_id']}</td>
            <td>{escape(str(item['reference_label']))}</td>
            <td>{escape(str(item['spoken_text']))}</td>
            <td>{escape(str(item['verbal_emotion']))}</td>
            <td>{escape(str(item['answer_evaluation']))}</td>
            <td>{escape(str(item['dominant_facial_expression'] or 'N/A'))}</td>
            <td>{escape(str(item['verbal_facial_comparison']))}</td>
        </tr>
        """

    if not rows:
        rows = '<tr><td colspan="7">No completed scenarios.</td></tr>'

    styles = """
    <style>
        body {
            font-family: Arial, sans-serif;
            color: #203047;
            margin: 40px;
            line-height: 1.6;
        }
        h1, h2 { color: #174a75; }
        .subtitle { color: #66788a; }
        .section {
            background: #f1f6fa;
            padding: 18px;
            border-radius: 8px;
            margin: 20px 0;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }
        th, td {
            border: 1px solid #cad6df;
            padding: 8px;
            text-align: left;
            overflow-wrap: anywhere;
        }
        th { background: #e5eef5; }
        .note { font-size: 12px; color: #66788a; }
        @media print {
            body { margin: 15mm; }
            .section { break-inside: avoid; }
        }
    </style>
    """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>NAO Session Report</title>
        {styles}
    </head>
    <body>
        <h1>NAO Emotion Recognition</h1>
        <p class="subtitle">Technical Prototype Session Report</p>

        <p><strong>Session ID:</strong> {escape(session_id)}</p>
        <p><strong>Completed Scenarios:</strong>
        {report['completed_scenarios']} /
        {report['total_scenarios']}</p>

        <div class="section">
            <h2>Verbal Performance</h2>
            <p>Correct: {performance['correct']}</p>
            <p>Incorrect: {performance['incorrect']}</p>
            <p>Unclear: {performance['unclear']}</p>
            <p>Accuracy (excluding unclear):
            {accuracy_text}</p>
        </div>

        <div class="section">
            <h2>Facial Expression Analysis</h2>
            <p>Model Observations:
            {facial['model_observations']}</p>
            <p>Mock Observations Excluded:
            {facial['mock_observations_excluded']}</p>
            <p>Most Frequent Expression:
            {escape(str(facial['most_frequent_expression'] or 'N/A'))}</p>
        </div>

        <h2>Scenario Details</h2>
        <table>
            <tr>
                <th>ID</th>
                <th>Reference</th>
                <th>Spoken Response</th>
                <th>Verbal Emotion</th>
                <th>Evaluation</th>
                <th>Facial Expression</th>
                <th>Comparison</th>
            </tr>
            {rows}
        </table>

        <p class="note">
            Prototype report generated from predefined test scenarios.
            Mock facial observations are excluded from model results.
            This report is not a clinical assessment.
        </p>
    </body>
    </html>
    """
