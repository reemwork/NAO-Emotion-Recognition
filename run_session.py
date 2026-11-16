
"""NAO physical robot session coordinator.

Runs a real NAO session using SSH, NAOqi, FastAPI,
Whisper, Qwen, and ResMaskingNet.
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
            "%s %s: %s %s" %
            (method, path, error, detail[:400])
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


# This script runs inside NAO using Python 2.
# Do not use Python 3-only syntax here.
ROBOT_SCRIPT = r'''
from naoqi import ALProxy
import base64, os, time, sys

ip = "127.0.0.1"

tts = ALProxy("ALTextToSpeech", ip, 9559)
recorder = ALProxy("ALAudioRecorder", ip, 9559)
photo = ALProxy("ALPhotoCapture", ip, 9559)

question = base64.b64decode("__QUESTION_B64__")
label = "__LABEL__"

audio = "/home/nao/" + label + ".wav"
image = "/home/nao/" + label + ".jpg"

try:
    if os.path.exists(audio):
        os.unlink(audio)

    if os.path.exists(image):
        os.unlink(image)

    tts.say(question)

    recorder.startMicrophonesRecording(
        audio,
        "wav",
        16000,
        (0, 0, 1, 0)
    )

    try:
        time.sleep(2)

        photo.setCameraID(0)
        photo.setResolution(2)
        photo.setPictureFormat("jpg")

        returned = photo.takePicture(
            "/home/nao",
            label
        )

        if not os.path.isfile(image):
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
                    image = candidate
                    break

        time.sleep(6)

    finally:
        recorder.stopMicrophonesRecording()

    if not os.path.isfile(audio):
        raise RuntimeError("Audio not created")

    if not os.path.isfile(image):
        raise RuntimeError(
            "Camera image not created: " + str(returned)
        )

    print("__AUDIO__=" + audio)
    print("__IMAGE__=" + image)

except Exception as e:
    sys.stderr.write(
        "CAPTURE_ERROR: " + str(e) + "\n"
    )
    sys.exit(2)
'''


def capture_from_robot(ip, question, label, dest):
    """Capture audio and image from the physical NAO."""

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
        if line.startswith(
            ("__AUDIO__=", "__IMAGE__=")
        )
    )

    if (
        "__AUDIO__" not in outputs
        or "__IMAGE__" not in outputs
    ):
        raise IntegrationError(
            "Missing capture paths from NAO: "
            + p.stdout[-700:]
        )

    local_audio = dest / (safe_label + ".wav")
    local_image = dest / (safe_label + ".jpg")

    for remote, local in (
        (outputs["__AUDIO__"], local_audio),
        (outputs["__IMAGE__"], local_image)
    ):
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

    return local_audio, local_image


def upload_capture(sid, scenario_id, audio, image):
    """Upload NAO image and audio to the backend."""

    # Validate the active session and scenario before uploading.
    session = req("GET", "/api/session/" + sid)

    if (
        session.get("session_status") != "active"
        or session.get("active_scenario_id") != scenario_id
    ):
        raise IntegrationError(
            "Session/scenario mismatch. "
            "The requested scenario must be active before uploading."
        )

    # Upload the facial image first.
    with image.open("rb") as file:
        req(
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

    # Analyze the camera frame independently, before speech processing.
    # Its report observation remains available even if transcription fails.
    analyze_facial_expression(sid, scenario_id)

    # Upload audio for Whisper and Qwen evaluation.
    with audio.open("rb") as file:
        return req(
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


def analyze_facial_expression(sid, scenario_id):
    """Analyze the NAO camera image using ResMaskingNet.

    Facial analysis is independent of verbal correctness.
    A failure must not invalidate a successfully evaluated
    spoken response.
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

                    # Optional sample replay for offline testing.
                    if args.samples_dir:

                        audio = args.samples_dir / (
                            "scenario_%s.wav" % scenario_id
                        )

                        image = args.samples_dir / (
                            "scenario_%s.jpg" % scenario_id
                        )

                        if not (
                            audio.is_file()
                            and image.is_file()
                        ):
                            raise IntegrationError(
                                "Sample WAV/JPG not found "
                                "for scenario %s"
                                % scenario_id
                            )

                    else:

                        # Capture directly from physical NAO.
                        audio, image = capture_from_robot(
                            args.nao_ip,
                            question,
                            "nao_%s_%s"
                            % (sid[:8], scenario_id),
                            folder
                        )

                    # Upload and analyze the NAO frame independently,
                    # then process the recorded audio using Whisper/Qwen.
                    result = upload_capture(
                        sid,
                        scenario_id,
                        audio,
                        image
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
            "Replay scenario WAV/JPG files without NAO "
            "(offline testing only)"
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
