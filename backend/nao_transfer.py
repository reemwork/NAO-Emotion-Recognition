"""Session-aware transfer bridge for local captures or files on a physical NAO.

Run from the project root after POST /api/session/start and
POST /api/scenario/start. The bridge never selects a scenario by guessing
from filenames; the caller provides session_id and scenario_id explicitly.

The backend gives uploaded files their canonical names:
data/session_audio/<session_id>/scenario_<id>_<unique>.wav
data/session_frames/<session_id>/scenario_<id>_<unique>.jpg
"""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

import requests

DEFAULT_API = "http://127.0.0.1:8000"
DEFAULT_NAO_IP = os.environ.get("NAO_IP", "169.254.247.199")
# Matches Capture_Audio in the committed Choregraphe behavior.xar.
DEFAULT_NAO_AUDIO = "/home/nao/response.wav"


def fetch_active_scenario(session_id, scenario_id, api_url=DEFAULT_API):
    """Refuse to attach captures to a different or inactive scenario."""
    response = requests.get(
        f"{api_url.rstrip('/')}/api/session/{session_id}",
        timeout=15
    )
    response.raise_for_status()
    session = response.json()

    if (
        session.get("session_status") != "active"
        or session.get("active_scenario_id") != scenario_id
    ):
        raise RuntimeError(
            "Session/scenario mismatch. Start the requested scenario "
            "before transferring its captures."
        )
    return session


def upload_captures(
    session_id, scenario_id, *, audio_path=None, image_paths=(),
    api_url=DEFAULT_API
):
    """Send captures to existing FastAPI endpoints; keep model code untouched."""
    image_paths = list(image_paths)
    if audio_path is None and not image_paths:
        raise ValueError("Provide an audio file or at least one face image.")

    # Refuse stale/mismatched IDs before uploading any data.
    fetch_active_scenario(session_id, scenario_id, api_url)
    base = api_url.rstrip("/")
    fields = {"session_id": session_id, "scenario_id": str(scenario_id)}
    uploaded = {"images": [], "audio": None}

    # Upload camera frames before evaluating audio, so both capture orders
    # are supported by the backend's session linking logic.
    for name in image_paths:
        image = Path(name)
        if image.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            raise ValueError(f"Unsupported image extension: {image}")
        with image.open("rb") as file:
            response = requests.post(
                f"{base}/api/camera/session-frame",
                data=fields,
                files={"frame": (image.name, file, "image/jpeg")},
                timeout=40
            )
        response.raise_for_status()
        uploaded["images"].append(response.json())

    if audio_path is not None:
        audio = Path(audio_path)
        if audio.suffix.lower() != ".wav":
            raise ValueError("Audio must be a WAV file.")
        with audio.open("rb") as file:
            response = requests.post(
                f"{base}/api/audio/evaluate",
                data=fields,
                files={"audio": (audio.name, file, "audio/wav")},
                timeout=360
            )
        response.raise_for_status()
        uploaded["audio"] = response.json()

    return uploaded


def download_from_nao(nao_ip, remote_path, local_path):
    """Download an explicitly specified NAO file using the SSH/SCP setup."""
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "scp",
            f"nao@{nao_ip}:{remote_path}",
            str(local_path)
        ],
        check=True,
        timeout=90
    )
    return local_path


def main():
    """Parse CLI arguments and transfer the specified audio/images to an active scenario."""
    parser = argparse.ArgumentParser(
        description="Transfer NAO data to a specific session/scenario."
    )
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--scenario-id", type=int, required=True)
    parser.add_argument("--api-url", default=DEFAULT_API)
    parser.add_argument("--audio", type=Path, help="Local WAV file")
    parser.add_argument(
        "--image", type=Path, action="append", default=[],
        help="Local JPG/PNG file (can be repeated)"
    )
    parser.add_argument(
        "--nao-audio", action="store_true",
        help="Pull WAV from the configured robot microphone path"
    )
    parser.add_argument(
        "--remote-image", action="append", default=[],
        help="Explicit remote image file path (can be repeated)"
    )
    parser.add_argument("--nao-ip", default=DEFAULT_NAO_IP)
    parser.add_argument(
        "--remote-audio-path", default=DEFAULT_NAO_AUDIO
    )
    args = parser.parse_args()

    if args.audio and args.nao_audio:
        parser.error("Choose either --audio or --nao-audio.")

    try:
        with tempfile.TemporaryDirectory(prefix="nao_transfer_") as temp:
            folder = Path(temp)
            audio = args.audio
            images = list(args.image)

            if args.nao_audio:
                audio = download_from_nao(
                    args.nao_ip, args.remote_audio_path,
                    folder / f"scenario_{args.scenario_id}_audio.wav"
                )

            for index, remote_path in enumerate(args.remote_image, 1):
                # Explicit file path is required: Choregraphe camera output
                # is not guaranteed to be stored in the robot camera folder.
                ext = Path(remote_path).suffix.lower()
                if ext not in {".jpg", ".jpeg", ".png"}:
                    raise ValueError(f"Invalid remote image: {remote_path}")
                destination = folder / (
                    f"scenario_{args.scenario_id}_image_{index}{ext}"
                )
                images.append(
                    download_from_nao(args.nao_ip, remote_path, destination)
                )

            result = upload_captures(
                args.session_id, args.scenario_id,
                audio_path=audio,
                image_paths=images,
                api_url=args.api_url
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))

    except (requests.RequestException, OSError, RuntimeError,
            subprocess.CalledProcessError, ValueError) as error:
        parser.exit(status=1, message=f"Transfer failed: {error}\n")


if __name__ == "__main__":
    main()
