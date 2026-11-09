from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from PIL import Image
import os
from datetime import datetime
from backend.transcribe_audio import transcribe_audio
import subprocess
import glob
import re

app = FastAPI(
    title="NAO Emotion Training Backend",
    version="1.0"
)


scenarios_db = [
    {
        "id": 1,
        "emotion": "happy",
        "question": "Look at me! Am I happy or sad?",
        "options": ["Happy", "Sad"],
        "correct": "Happy",
        "image_url": "/static/images/happy_scenario.jpg"
    },
    {
        "id": 2,
        "emotion": "sad",
        "question": "How do I look now? Do I look sad or angry?",
        "options": ["Sad", "Angry"],
        "correct": "Sad",
        "image_url": "/static/images/sad_scenario.jpg"
    }
]


class ChildResponse(BaseModel):
    scenario_id: int
    spoken_text: str


@app.get("/")
def read_root():
    return {
        "status": "online"
    }


@app.post("/api/session/start")
def start_session():
    return {
        "status": "success",
        "total_scenarios": len(scenarios_db)
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


@app.post("/api/response/submit")
def submit_response(data: ChildResponse):
    return {
        "status": "success",
        "message": "Response received and logged successfully",
        "scenario_id": data.scenario_id,
        "received_text": data.spoken_text
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