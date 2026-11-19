
import re
import subprocess
from pathlib import Path


FRAME_COUNT = 4
CAPTURE_SECONDS = 8

ROBOT_SCRIPT = r'''
from naoqi import ALProxy
import os
import sys
import time

recorder = ALProxy("ALAudioRecorder", "127.0.0.1", 9559)
camera = ALProxy("ALPhotoCapture", "127.0.0.1", 9559)

label = "__LABEL__"
audio_path = "/home/nao/" + label + ".wav"
images = []
recording_started = False

try:
    # Configure the NAO camera before starting audio capture.
    camera.setCameraID(0)
    camera.setResolution(2)
    camera.setPictureFormat("jpg")

    if os.path.exists(audio_path):
        os.remove(audio_path)

    # Start recording using the front microphone.
    recorder.startMicrophonesRecording(
        audio_path,
        "wav",
        16000,
        (0, 0, 1, 0)
    )
    recording_started = True
    start = time.time()

    # Capture four images during the recording.
    capture_times = (1, 3, 5, 7)

    for index, second in enumerate(capture_times, start=1):
        remaining = second - (time.time() - start)

        if remaining > 0:
            time.sleep(remaining)

        name = label + "_frame_" + str(index)
        expected_path = "/home/nao/" + name + ".jpg"

        if os.path.exists(expected_path):
            os.remove(expected_path)

        returned = camera.takePicture("/home/nao", name)
        path = expected_path

        # NAOqi may return the actual saved image path.
        if not os.path.isfile(path):
            candidates = (
                returned if isinstance(returned, (list, tuple))
                else [returned]
            )

            for candidate in candidates:
                if (
                    isinstance(candidate, basestring)
                    and os.path.isfile(candidate)
                ):
                    path = candidate
                    break

        if not os.path.isfile(path):
            raise RuntimeError(
                "Camera frame %s was not created" % index
            )

        images.append(path)

    # Keep the audio recording active for eight seconds.
    remaining = 8 - (time.time() - start)

    if remaining > 0:
        time.sleep(remaining)

finally:
    if recording_started:
        try:
            recorder.stopMicrophonesRecording()
        except Exception as error:
            sys.stderr.write(
                "STOP_RECORDING_ERROR: " + str(error) + "\n"
            )
            raise

# Verify all expected files.
if not os.path.isfile(audio_path):
    raise RuntimeError("Audio recording was not created")

if os.path.getsize(audio_path) == 0:
    raise RuntimeError("Audio recording is empty")

if len(images) != 4:
    raise RuntimeError("Incomplete camera capture")

for path in images:
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise RuntimeError("Invalid camera image: " + path)

# Print file paths for the external computer.
print("__AUDIO__=" + audio_path)

for index, path in enumerate(images, start=1):
    print("__IMAGE_%s__=%s" % (index, path))
'''


def capture_from_nao(
    nao_ip,
    capture_id,
    output_dir,
    delete_remote=False
):
    """
    Capture data from the physical NAO robot.

    Records:
        - One WAV audio file
        - Four camera images

    Transfers files from NAO to the external computer.

    Returns:
        audio_path, image_paths
    """

    capture_id = re.sub(
        r"[^A-Za-z0-9_]",
        "_",
        str(capture_id)
    )

    if not capture_id:
        raise ValueError("capture_id cannot be empty")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    script = ROBOT_SCRIPT.replace(
        "__LABEL__",
        capture_id
    )

    ssh_command = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8",
        "nao@" + nao_ip,
        (
            "env PYTHONPATH="
            "/opt/aldebaran/lib/python2.7/site-packages:"
            "/opt/aldebaran/lib "
            "python -"
        ),
    ]

    try:
        result = subprocess.run(
            ssh_command,
            input=script,
            capture_output=True,
            text=True,
            timeout=100,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            "NAO capture timed out"
        ) from error

    if result.returncode != 0:
        raise RuntimeError(
            "NAO capture failed: "
            + result.stderr[-1000:]
        )

    # Extract the paths returned by NAO.
    paths = {}

    for line in result.stdout.splitlines():
        if (
            line.startswith("__AUDIO__=")
            or re.match(r"^__IMAGE_[1-4]__=", line)
        ):
            key, value = line.split("=", 1)
            paths[key] = value.strip()

    required_keys = ["__AUDIO__"] + [
        "__IMAGE_%s__" % index
        for index in range(1, FRAME_COUNT + 1)
    ]

    missing = [
        key for key in required_keys
        if key not in paths
    ]

    if missing:
        raise RuntimeError(
            "Missing NAO capture paths: "
            + ", ".join(missing)
        )

    audio_path = output_dir / (
        capture_id + ".wav"
    )

    image_paths = [
        output_dir / (
            capture_id + "_frame_%s.jpg" % index
        )
        for index in range(1, FRAME_COUNT + 1)
    ]

    destinations = [audio_path] + image_paths
    remote_paths = []

    # Transfer the captured files.
    for key, destination in zip(
        required_keys,
        destinations
    ):
        remote_path = paths[key]

        if not remote_path.startswith("/home/nao/"):
            raise RuntimeError(
                "Invalid NAO file path: " + remote_path
            )

        remote_paths.append(remote_path)

        try:
            subprocess.run(
                [
                    "scp",
                    "-o", "BatchMode=yes",
                    "-o", "ConnectTimeout=8",
                    "nao@" + nao_ip + ":" + remote_path,
                    str(destination),
                ],
                check=True,
                timeout=90,
            )
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired
        ) as error:
            raise RuntimeError(
                "Failed to transfer: " + remote_path
            ) from error

        if (
            not destination.is_file()
            or destination.stat().st_size == 0
        ):
            raise RuntimeError(
                "Transferred file is empty or missing: "
                + str(destination)
            )

    # Optional cleanup after successful transfer.
    if delete_remote:
        cleanup_script = (
            "import os\n"
            "paths = " + repr(remote_paths) + "\n"
            "for path in paths:\n"
            "    if path.startswith('/home/nao/') "
            "and os.path.isfile(path):\n"
            "        os.remove(path)\n"
        )

        subprocess.run(
            ssh_command,
            input=cleanup_script,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

    return audio_path, image_paths
