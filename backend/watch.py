import os
import time
import subprocess
import glob
import re

NAO_IP = "169.254.247.199"

REMOTE_CAMERA = "/home/nao/recordings/cameras"
# Legacy watcher for standalone NAO acquisition; does not tag sessions.
# For session-aware uploads, run: python -m backend.nao_transfer --help
# Matches the audio path saved by the current Choregraphe behavior.xar.
REMOTE_AUDIO = "/home/nao/response.wav"

LOCAL_IMAGES = "data/nao_frames"
LOCAL_AUDIO = "data/nao_audio"

os.makedirs(LOCAL_IMAGES, exist_ok=True)
os.makedirs(LOCAL_AUDIO, exist_ok=True)

downloaded_images = set(os.listdir(LOCAL_IMAGES))


def get_next_audio_number():
    files = glob.glob(os.path.join(LOCAL_AUDIO, "response_*.wav"))

    numbers = []

    for file in files:
        match = re.search(
            r"response_(\d+)\.wav$",
            os.path.basename(file)
        )

        if match:
            numbers.append(int(match.group(1)))

    return max(numbers, default=0) + 1


def get_audio_mtime():
    result = subprocess.run(
        [
            "ssh",
            f"nao@{NAO_IP}",
            f"stat -c %Y {REMOTE_AUDIO} 2>/dev/null"
        ],
        capture_output=True,
        text=True
    )

    return result.stdout.strip()


last_audio_mtime = get_audio_mtime()

print("Watching NAO...")
print("Waiting for new images and audio...")
print("Current audio:", last_audio_mtime)
print()


while True:
    try:

        # CAMERA
        result = subprocess.run(
            [
                "ssh",
                f"nao@{NAO_IP}",
                f"ls -1 {REMOTE_CAMERA}/*.jpg 2>/dev/null"
            ],
            capture_output=True,
            text=True
        )

        remote_images = result.stdout.strip().splitlines()

        for remote_image in remote_images:
            filename = os.path.basename(remote_image)

            if filename not in downloaded_images:

                local_path = os.path.join(
                    LOCAL_IMAGES,
                    filename
                )

                subprocess.run(
                    [
                        "scp",
                        f"nao@{NAO_IP}:{remote_image}",
                        local_path
                    ],
                    check=True
                )

                downloaded_images.add(filename)

                print("New image:")
                print(local_path)
                print()

        # AUDIO
        current_audio_mtime = get_audio_mtime()

        if (
            current_audio_mtime
            and current_audio_mtime != last_audio_mtime
        ):

            print("New recording detected.")

            # Record Sound is 8 seconds.
            # Give NAO enough time to finish writing the WAV.
            time.sleep(10)

            next_number = get_next_audio_number()

            filename = f"response_{next_number}.wav"

            local_path = os.path.join(
                LOCAL_AUDIO,
                filename
            )

            subprocess.run(
                [
                    "scp",
                    f"nao@{NAO_IP}:{REMOTE_AUDIO}",
                    local_path
                ],
                check=True
            )

            last_audio_mtime = get_audio_mtime()

            print("New audio saved:")
            print(local_path)
            print()

        time.sleep(1)

    except KeyboardInterrupt:
        print("\nWatcher stopped.")
        break

    except Exception as e:
        print("Error:", e)
        time.sleep(2)