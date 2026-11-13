"""NAO audio API: WAV uploads, robot transfers, Whisper transcription, evaluation.

Whisper itself is loaded by backend.transcribe_audio for compatibility with
existing standalone transcription scripts; this module owns the complete
request processing workflow without changing the selected STT model.
"""

import glob
import os
import re
import subprocess
from datetime import datetime
from importlib import import_module
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from backend.transcribe_audio import model as whisper_model, transcribe_audio

router = APIRouter(tags=["Audio / Speech-to-Text"])


def _backend():
    """Access shared session state lazily; avoids import cycles."""
    return import_module("backend.app")


@router.post("/api/audio/upload")
async def upload_nao_audio(audio: UploadFile = File(...)):
    transcribe_audio = _backend().transcribe_audio
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

@router.post("/api/audio/capture")
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


@router.post("/api/audio/evaluate")
def evaluate_audio(
    session_id: str = Form(...),
    scenario_id: int = Form(...),
    audio: UploadFile = File(...)
):
    ctx = _backend()
    sessions = ctx.sessions
    scenarios_db = ctx.scenarios_db
    ROOT = ctx.ROOT
    whisper_model = ctx.whisper_model
    record_scenario_issue = ctx.record_scenario_issue
    submit_response = ctx.submit_response
    ChildResponse = ctx.ChildResponse
    save_sessions = ctx.save_sessions

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
        record_scenario_issue(session, scenario_id, "transcription_failed")
        audio_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=500,
            detail="Audio transcription failed."
        ) from error

    if not transcript:
        record_scenario_issue(session, scenario_id, "no_speech_recognized")
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
