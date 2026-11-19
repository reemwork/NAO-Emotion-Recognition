
"""NAO audio API: WAV uploads, robot transfers, and Whisper evaluation.

The session-based workflow uses English Whisper transcription followed
by text-only Qwen classification through the verbal response endpoint.

Legacy upload and SCP endpoints remain available for compatibility.
"""

import glob
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

import backend
from backend.transcribe_audio import model as whisper_model
from backend.transcribe_audio import transcribe_audio


router = APIRouter(tags=["Audio / Speech-to-Text"])

MAX_AUDIO_BYTES = 20 * 1024 * 1024
SCP_TIMEOUT = 60


def _backend():
    """Access shared state without triggering circular imports."""
    return backend.app


def _read_wav(audio: UploadFile):
    """Read a bounded WAV upload and validate its container header."""
    if not (audio.filename or "").lower().endswith(".wav"):
        raise HTTPException(
            status_code=400,
            detail="Only WAV audio files are supported."
        )

    data = audio.file.read(MAX_AUDIO_BYTES + 1)

    if not data or len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=400,
            detail="Audio must be non-empty and at most 20 MB."
        )

    if (
        len(data) < 12
        or data[:4] != b"RIFF"
        or data[8:12] != b"WAVE"
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid WAV file."
        )

    return data


@router.post("/api/audio/upload")
async def upload_nao_audio(audio: UploadFile = File(...)):
    """Save and transcribe a standalone WAV upload.

    This legacy endpoint is not linked to a training session.
    Its transcription helper retains its existing language settings.
    """
    transcribe = _backend().transcribe_audio

    folder = Path("data/nao_audio")
    folder.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    audio_path = folder / f"response_{timestamp}.wav"
    text_path = folder / f"response_{timestamp}.txt"

    # The legacy endpoint also uses bounded WAV validation.
    audio_data = await audio.read(MAX_AUDIO_BYTES + 1)

    if not audio_data or len(audio_data) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=400,
            detail="Audio must be non-empty and at most 20 MB."
        )

    if (
        len(audio_data) < 12
        or audio_data[:4] != b"RIFF"
        or audio_data[8:12] != b"WAVE"
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid WAV file."
        )

    audio_path.write_bytes(audio_data)

    try:
        transcript = transcribe(str(audio_path))
    except Exception as error:
        audio_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail="Audio transcription failed."
        ) from error

    text_path.write_text(transcript, encoding="utf-8")

    return {
        "status": "success",
        "message": "NAO audio saved and transcribed successfully",
        "audio_file": str(audio_path),
        "text_file": str(text_path),
        "transcript": transcript
    }


@router.post("/api/audio/capture")
def capture_nao_audio():
    """Copy a pre-recorded WAV file from NAO using SCP.

    NAO_IP may be supplied as an environment variable.
    The previous IP remains a fallback for legacy usage.
    """
    nao_ip = os.environ.get("NAO_IP", "169.254.247.199")
    remote_audio = "/home/nao/recordings/microphones/response.wav"

    folder = Path("data/nao_audio")
    folder.mkdir(parents=True, exist_ok=True)

    numbers = []

    for path in glob.glob(str(folder / "response_*.wav")):
        match = re.fullmatch(
            r"response_(\d+)\.wav",
            Path(path).name
        )

        if match:
            numbers.append(int(match.group(1)))

    next_number = max(numbers, default=0) + 1
    audio_path = folder / f"response_{next_number}.wav"

    try:
        subprocess.run(
            [
                "scp",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=10",
                f"nao@{nao_ip}:{remote_audio}",
                str(audio_path)
            ],
            check=True,
            timeout=SCP_TIMEOUT
        )

    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        OSError
    ) as error:
        audio_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=502,
            detail="Failed to download audio from NAO."
        ) from error

    return {
        "status": "success",
        "message": "NAO audio downloaded successfully",
        "audio_file": str(audio_path)
    }


@router.post("/api/audio/evaluate")
def evaluate_audio(
    session_id: str = Form(...),
    scenario_id: int = Form(...),
    audio: UploadFile = File(...)
):
    """Transcribe an active scenario's WAV and evaluate its verbal answer."""
    ctx = _backend()

    session = ctx.sessions.get(session_id)

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

    if not any(
        item["scenario_id"] == scenario_id
        for item in ctx.scenarios_db
    ):
        raise HTTPException(
            status_code=404,
            detail="Scenario not found."
        )

    # Reject mismatched or inactive scenarios before running Whisper.
    if (
        session.get("active_scenario_id") != scenario_id
        or session.get("scenario_progress", {})
            .get(str(scenario_id), {})
            .get("status") != "in_progress"
    ):
        raise HTTPException(
            status_code=409,
            detail="Audio does not match the active scenario."
        )

    if any(
        result["scenario_id"] == scenario_id
        for result in session["results"]
    ):
        raise HTTPException(
            status_code=409,
            detail="Response already submitted for this scenario."
        )

    audio_data = _read_wav(audio)

    audio_folder = (
        ctx.ROOT / "data" / "session_audio" / session_id
    )
    audio_folder.mkdir(parents=True, exist_ok=True)

    audio_path = (
        audio_folder
        / f"scenario_{scenario_id}_{uuid4().hex[:8]}.wav"
    )
    audio_path.write_bytes(audio_data)

    # Step 1: Whisper converts speech to English text.
    try:
        whisper_result = ctx.whisper_model.transcribe(
            str(audio_path),
            language="en",
            fp16=False
        )
        transcript = whisper_result["text"].strip()

    except Exception as error:
        ctx.record_scenario_issue(
            session, scenario_id, "transcription_failed"
        )
        audio_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=500,
            detail="Audio transcription failed."
        ) from error

    if not transcript:
        ctx.record_scenario_issue(
            session, scenario_id, "no_speech_recognized"
        )
        audio_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=422,
            detail="No speech was recognized."
        )

    # Step 2: Send text only to Qwen and compare its predicted
    # emotion against the predefined scenario reference label.
    try:
        response = ctx.submit_response(
            ctx.ChildResponse(
                session_id=session_id,
                scenario_id=scenario_id,
                spoken_text=transcript
            )
        )

    except HTTPException:
        audio_path.unlink(missing_ok=True)
        raise

    # Step 3: Attach the audio source to the saved verbal result.
    relative_audio_path = audio_path.relative_to(ctx.ROOT)

    response["saved_result"]["audio_file"] = (
        relative_audio_path.as_posix()
    )

    ctx.save_sessions()
    return response
