
"""NAO physical robot session coordinator.

Runs a real NAO session using SSH, NAOqi, FastAPI,
Whisper, Qwen, and ResMaskingNet.

Physical NAO sessions capture 4 frames per scenario.
Legacy single-image calls remain supported for testing.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent

API = "http://127.0.0.1:8000"
OLLAMA = "http://127.0.0.1:11434"
MODEL = "qwen2.5vl:3b"

FRAME_COUNT = 4

# NAO V6 uses Python 2 NAOqi bindings.
NAO_PYTHON_COMMAND = (
    'env PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages:'
    '/opt/aldebaran/lib python -'
)


class IntegrationError(RuntimeError):
    pass


def req(method, path, **kwargs):
    """Send a request to the FastAPI backend."""
    try:
        res = requests.request(
            method,
            API + path,
            timeout=kwargs.pop("timeout", 30),
            **kwargs
        )

        res.raise_for_status()
        return res.json()

    except requests.RequestException as error:
        detail = getattr(
            getattr(error, "response", None),
            "text",
            ""
        )

        raise IntegrationError(
            "%s %s: %s %s"
            % (method, path, error, detail[:400])
        ) from error


def robot_ssh_command(ip):
    """Build the SSH command for NAO."""
    return [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8",
        "nao@" + ip,
        NAO_PYTHON_COMMAND
    ]


def probe_robot(ip):
    """Verify SSH and NAOqi availability."""
    p = subprocess.run(
        robot_ssh_command(ip),
        input='import naoqi\nprint("NAOQI_OK")\n',
        capture_output=True,
        text=True,
        timeout=16
    )

    if p.returncode or "NAOQI_OK" not in p.stdout:
        raise IntegrationError(
            "Robot SSH/NAOqi check failed: "
            + (
                p.stderr
                or p.stdout
                or "No output from robot"
            ).strip()[-500:]
        )


def preflight(ip, check_robot=True):
    """Check backend, Ollama model, and NAO."""
    req("GET", "/")

    try:
        r = requests.get(
            OLLAMA + "/api/tags",
            timeout=10
        )

        r.raise_for_status()

        names = [
            x.get("name", "")
            for x in r.json().get("models", [])
        ]

        if MODEL not in names:
            raise IntegrationError(
                "Ollama model %s missing. Installed models: %s"
                % (MODEL, names)
            )

    except requests.RequestException as error:
        raise IntegrationError(
            "Ollama unreachable at %s: %s"
            % (OLLAMA, error)
        ) from error

    if check_robot:
        probe_robot(ip)


# ============================================================
# ROBOT SCRIPT - PYTHON 2
# ============================================================

# This script runs inside NAO using Python 2.
# Do not use Python 3-only syntax here.

ROBOT_SCRIPT = r'''
from naoqi import ALProxy
import base64
import os
import time
import sys

ip = "127.0.0.1"

tts = ALProxy("ALTextToSpeech", ip, 9559)
recorder = ALProxy("ALAudioRecorder", ip, 9559)
photo = ALProxy("ALPhotoCapture", ip, 9559)

question = base64.b64decode("__QUESTION_B64__")
label = "__LABEL__"

audio = "/home/nao/" + label + ".wav"
images = []

try:
    if os.path.exists(audio):
        os.unlink(audio)

    # Ask the question before recording.
    tts.say(question)

    recorder.startMicrophonesRecording(
        audio,
        "wav",
        16000,
        (0, 0, 1, 0)
    )

    try:
        photo.setCameraID(0)
        photo.setResolution(2)
        photo.setPictureFormat("jpg")

        started = time.time()

        # Target capture times: 1, 3, 5, 7 seconds.
        capture_times = (1, 3, 5, 7)

        for i, target in enumerate(capture_times):

            remaining = target - (time.time() - started)

            if remaining > 0:
                time.sleep(remaining)

            frame_label = (
                label + "_frame_" + str(i + 1)
            )

            frame_path = (
                "/home/nao/" + frame_label + ".jpg"
            )

            if os.path.exists(frame_path):
                os.unlink(frame_path)

            returned = photo.takePicture(
                "/home/nao",
                frame_label
            )

            if not os.path.isfile(frame_path):

                candidates = (
                    returned
                    if isinstance(returned, (list, tuple))
                    else [returned]
                )

                for candidate in candidates:
                    if (
                        isinstance(candidate, basestring)
                        and os.path.isfile(candidate)
                    ):
                        frame_path = candidate
                        break

            if not os.path.isfile(frame_path):
                raise RuntimeError(
                    "Frame %s was not created"
                    % (i + 1)
                )

            images.append(frame_path)

            print(
                "Captured frame %s: %s"
                % (i + 1, frame_path)
            )

        # Keep recording until at least 8 seconds.
        remaining = 8 - (time.time() - started)

        if remaining > 0:
            time.sleep(remaining)

    finally:
        recorder.stopMicrophonesRecording()

    if not os.path.isfile(audio):
        raise RuntimeError("Audio not created")

    if len(images) != 4:
        raise RuntimeError(
            "Expected 4 frames, got %s"
            % len(images)
        )

    print("__AUDIO__=" + audio)

    for i, image in enumerate(images):
        print(
            "__IMAGE_%s__=%s"
            % (i + 1, image)
        )

except Exception as e:
    sys.stderr.write(
        "CAPTURE_ERROR: " + str(e) + "\n"
    )
    sys.exit(2)
'''


# ============================================================
# CAPTURE AND TRANSFER FROM NAO
# ============================================================

def capture_from_robot(ip, question, label, dest):
    """Capture audio and 4 images from the physical NAO."""

    safe_label = re.sub(
        r"[^A-Za-z0-9_]",
        "_",
        label
    )

    encoded_question = base64.b64encode(
        question.encode("utf-8")
    ).decode("ascii")

    src = (
        ROBOT_SCRIPT
        .replace("__QUESTION_B64__", encoded_question)
        .replace("__LABEL__", safe_label)
    )

    p = subprocess.run(
        robot_ssh_command(ip),
        input=src,
        capture_output=True,
        text=True,
        timeout=100
    )

    if p.returncode:
        raise IntegrationError(
            "NAO capture failed: "
            + (p.stderr or p.stdout)[-900:]
        )

    outputs = dict(
        line.split("=", 1)
        for line in p.stdout.splitlines()
        if line.startswith("__AUDIO__=")
        or re.match(r"^__IMAGE_[1-4]__=", line)
    )

    required = ["__AUDIO__"] + [
        "__IMAGE_%s__" % i
        for i in range(1, FRAME_COUNT + 1)
    ]

    missing = [
        key for key in required
        if key not in outputs
    ]

    if missing:
        raise IntegrationError(
            "Missing capture paths from NAO: %s. Output: %s"
            % (missing, p.stdout[-700:])
        )

    local_audio = dest / (safe_label + ".wav")

    local_images = [
        dest / (
            safe_label + "_frame_" + str(i) + ".jpg"
        )
        for i in range(1, FRAME_COUNT + 1)
    ]

    transfers = [
        (outputs["__AUDIO__"], local_audio)
    ]

    for i, local_image in enumerate(local_images, start=1):
        transfers.append(
            (
                outputs["__IMAGE_%s__" % i],
                local_image
            )
        )

    for remote, local in transfers:

        if not remote.startswith("/home/nao/"):
            raise IntegrationError(
                "Unsafe remote capture path: " + remote
            )

        subprocess.run(
            [
                "scp",
                "-o", "BatchMode=yes",
                "nao@" + ip + ":" + remote,
                str(local)
            ],
            check=True,
            timeout=90
        )

        if not local.is_file() or not local.stat().st_size:
            raise IntegrationError(
                "Empty capture: " + str(local)
            )

    print(
        "Transferred audio and %s frames from NAO."
        % len(local_images)
    )

    return local_audio, local_images


# ============================================================
# FACIAL ANALYSIS
# ============================================================

def analyze_facial_expression(sid, scenario_id):
    """Analyze the latest uploaded frame using ResMaskingNet.

    Facial analysis is independent of verbal correctness.
    A failed facial evaluation must not invalidate a
    successfully evaluated spoken response.
    """

    try:
        result = req(
            "POST",
            "/api/facial/evaluate",
            json={
                "session_id": sid,
                "scenario_id": scenario_id
            },
            timeout=240
        )

        print(
            "Facial analysis:",
            json.dumps(
                result,
                ensure_ascii=False
            )[:900]
        )

        return result

    except IntegrationError as error:
        print(
            "WARNING: Facial analysis unavailable:",
            error
        )

        return None


# ============================================================
# UPLOAD CAMERA FRAMES AND AUDIO
# ============================================================

def upload_capture(sid, scenario_id, audio, images):
    """Upload camera frames and audio to the backend.

    Supports:
      - A single Path (legacy tests)
      - A list of 4 Paths (physical NAO workflow)
    """

    # Backward compatibility with single-image callers.
    if isinstance(images, (str, Path)):
        images = [Path(images)]
    else:
        images = [Path(image) for image in images]

    audio = Path(audio)

    # Validate the active session and scenario.
    session = req(
        "GET",
        "/api/session/" + sid
    )

    if (
        session.get("session_status") != "active"
        or session.get("active_scenario_id") != scenario_id
    ):
        raise IntegrationError(
            "Session/scenario mismatch. "
            "The requested scenario must be active before uploading."
        )

    if len(images) not in (1, FRAME_COUNT):
        raise IntegrationError(
            "Expected 1 or %s frames, got %s"
            % (FRAME_COUNT, len(images))
        )

    successful_observations = 0

    for i, image in enumerate(images, start=1):

        if not image.is_file():
            raise IntegrationError(
                "Image not found: " + str(image)
            )

        print(
            "Uploading frame %s/%s: %s"
            % (i, len(images), image.name)
        )

        # Upload one frame.
        with image.open("rb") as file:
            upload_result = req(
                "POST",
                "/api/camera/session-frame",
                data={
                    "session_id": sid,
                    "scenario_id": str(scenario_id)
                },
                files={
                    "frame": (
                        image.name,
                        file,
                        "image/jpeg"
                    )
                },
                timeout=60
            )

        print(
            "Frame saved:",
            upload_result.get("image_file")
        )

        # The backend analyzes the latest frame.
        # Analyze immediately after each upload.
        facial_result = analyze_facial_expression(
            sid,
            scenario_id
        )

        if (
            facial_result is not None
            and facial_result.get("facial_result")
        ):
            successful_observations += 1

    print(
        "Facial observations: %s/%s"
        % (successful_observations, len(images))
    )

    # Process the audio using Whisper and Qwen.
    if not audio.is_file():
        raise IntegrationError(
            "Audio file not found: " + str(audio)
        )

    with audio.open("rb") as file:
        result = req(
            "POST",
            "/api/audio/evaluate",
            data={
                "session_id": sid,
                "scenario_id": str(scenario_id)
            },
            files={
                "audio": (
                    audio.name,
                    file,
                    "audio/wav"
                )
            },
            timeout=360
        )

    return result


# ============================================================
# DISPLAY SCENARIO
# ============================================================

def show_image(scenario):
    """Display the scenario image on the laptop screen."""

    rel = scenario.get("image_path", "")

    path = (ROOT / rel).resolve()

    if ROOT not in path.parents or not path.is_file():
        print(
            "WARNING: scenario image missing:",
            rel
        )
        return

    webbrowser.open(path.as_uri())


# ============================================================
# RUN COMPLETE SESSION
# ============================================================

def run(args):
    """Run a complete NAO emotion recognition session."""

    print("Checking backend, local MLLM and robot...")

    preflight(
        args.nao_ip,
        not args.samples_dir
    )

    print("Preflight OK.")

    sid = req(
        "POST",
        "/api/session/start"
    )["session_id"]

    print("Session:", sid)

    try:
        with tempfile.TemporaryDirectory(
            prefix="nao_session_"
        ) as tmp:

            folder = Path(tmp)
            index = 0

            while True:

                response = req(
                    "GET",
                    "/api/scenario/next",
                    params={"index": index}
                )

                if not response.get("has_more"):
                    break

                scenario = response["scenario"]

                scenario_id = int(
                    scenario["scenario_id"]
                )

                print(
                    "\nScenario %s - reference label: %s"
                    % (
                        scenario_id,
                        scenario["reference_label"]
                    )
                )

                # Start the current scenario.
                req(
                    "POST",
                    "/api/scenario/start",
                    json={
                        "session_id": sid,
                        "scenario_id": scenario_id
                    }
                )

                # Display the emotional image.
                show_image(scenario)

                question = args.question

                try:

                    # Offline testing without NAO.
                    if args.samples_dir:

                        audio = args.samples_dir / (
                            "scenario_%s.wav" % scenario_id
                        )

                        images = [
                            args.samples_dir / (
                                "scenario_%s_frame_%s.jpg"
                                % (scenario_id, i)
                            )
                            for i in range(
                                1,
                                FRAME_COUNT + 1
                            )
                        ]

                        if (
                            not audio.is_file()
                            or not all(
                                image.is_file()
                                for image in images
                            )
                        ):
                            raise IntegrationError(
                                "Sample WAV/JPG not found "
                                "for scenario %s"
                                % scenario_id
                            )

                    else:

                        # Capture directly from physical NAO.
                        audio, images = capture_from_robot(
                            args.nao_ip,
                            question,
                            "nao_%s_%s"
                            % (sid[:8], scenario_id),
                            folder
                        )

                    # Upload and analyze camera frames,
                    # then process audio using Whisper/Qwen.
                    result = upload_capture(
                        sid,
                        scenario_id,
                        audio,
                        images
                    )

                    print(
                        "Evaluated:",
                        json.dumps(
                            result,
                            ensure_ascii=False
                        )[:900]
                    )

                    # Mark the scenario as completed.
                    req(
                        "POST",
                        "/api/scenario/complete",
                        json={
                            "session_id": sid,
                            "scenario_id": scenario_id
                        }
                    )

                    print(
                        "Scenario %s completed."
                        % scenario_id
                    )

                except (
                    IntegrationError,
                    subprocess.CalledProcessError,
                    subprocess.TimeoutExpired
                ) as error:

                    print(
                        "WARNING: scenario %s failed: %s"
                        % (scenario_id, error)
                    )

                    reason = "processing_failed"

                    if "Sample WAV/JPG not found" in str(error):
                        reason = "no_response"

                    req(
                        "POST",
                        "/api/scenario/recovery",
                        json={
                            "session_id": sid,
                            "scenario_id": scenario_id,
                            "action": "skip",
                            "reason": reason
                        }
                    )

                index += 1

    finally:

        # Finalize the session and generate its report.
        try:

            session = req(
                "GET",
                "/api/session/" + sid
            )

            active = session.get(
                "active_scenario_id"
            )

            if active is not None:
                req(
                    "POST",
                    "/api/scenario/recovery",
                    json={
                        "session_id": sid,
                        "scenario_id": active,
                        "action": "skip",
                        "reason": "processing_failed"
                    }
                )

            req(
                "POST",
                "/api/session/end",
                json={"session_id": sid}
            )

            report = req(
                "GET",
                "/api/session/" + sid + "/report"
            )

            output = (
                ROOT
                / "data"
                / ("session_%s_report.json" % sid)
            )

            output.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            output.write_text(
                json.dumps(
                    report,
                    indent=2,
                    ensure_ascii=False
                ),
                encoding="utf-8"
            )

            print(
                "\nReport saved:",
                output
            )

            print(
                "HTML report:",
                API
                + "/api/session/"
                + sid
                + "/report/view"
            )

        except Exception as error:
            print(
                "WARNING: could not finalize session: %s"
                % error
            )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=(
            "Run NAO scenarios via existing FastAPI backend"
        )
    )

    parser.add_argument(
        "--nao-ip",
        default=os.environ.get(
            "NAO_IP",
            "169.254.247.199"
        )
    )

    parser.add_argument(
        "--question",
        default=(
            "What emotion do you see in this picture?"
        )
    )

    parser.add_argument(
        "--samples-dir",
        type=Path,
        help=(
            "Replay scenario WAV and 4 JPG frames "
            "without NAO (offline testing only)"
        )
    )

    args = parser.parse_args()

    try:
        run(args)

    except (
        IntegrationError,
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired
    ) as error:

        print(
            "ERROR:",
            error,
            file=sys.stderr
        )

        sys.exit(1)
