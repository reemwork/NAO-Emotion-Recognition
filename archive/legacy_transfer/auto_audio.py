"""ARCHIVED continuous NAO WAV watcher; retained for historical reference.

Polls a fixed NAO WAV path over SSH, waits for its file size to stabilize,
and downloads new recordings with sequential filenames. No session IDs
are attached; use backend.nao_transfer for session-aware transfers.
"""

import os
import time
import glob
import re
import subprocess

NAO_IP = "169.254.247.199"

REMOTE_AUDIO = "/home/nao/recordings/microphones/response.wav"
LOCAL_AUDIO = "data/nao_audio"

os.makedirs(LOCAL_AUDIO, exist_ok=True)


def get_remote_info():
    """Read the robot WAV modification time and size using an SSH stat command."""
    result = subprocess.run(
        [
            "ssh",
            f"nao@{NAO_IP}",
            f"stat -c '%Y %s' {REMOTE_AUDIO} 2>/dev/null"
        ],
        capture_output=True,
        text=True
    )

    output = result.stdout.strip()

    if not output:
        return None

    parts = output.split()

    return parts[0], int(parts[1])


def get_next_number():
    """Return the next sequential local response_<number>.wav index."""
    files = glob.glob(
        os.path.join(LOCAL_AUDIO, "response_*.wav")
    )

    numbers = []

    for file in files:
        filename = os.path.basename(file)

        match = re.fullmatch(
            r"response_(\d+)\.wav",
            filename
        )

        if match:
            numbers.append(int(match.group(1)))

    return max(numbers, default=0) + 1


def wait_until_finished():
    """Wait until three successive size checks show a stable recording."""
    previous_size = None
    stable_count = 0

    # Do not copy a WAV file while NAO is still writing audio data.
    while stable_count < 3:
        info = get_remote_info()

        if info is None:
            time.sleep(1)
            continue

        _, size = info

        if size == previous_size:
            stable_count += 1
        else:
            previous_size = size
            stable_count = 0

        time.sleep(1)


current_info = get_remote_info()

if current_info is None:
    print("Error: Could not find NAO recording.")
    exit()

last_mtime = current_info[0]

print("NAO audio watcher is running...")
print("Waiting for a NEW recording...")
print("Current recording:", last_mtime)
print()


# This loop runs immediately if imported; execute as a script only.
while True:
    try:
        current_info = get_remote_info()

        if current_info is None:
            time.sleep(1)
            continue

        current_mtime = current_info[0]

        if current_mtime != last_mtime:

            print("New recording detected.")
            print("Waiting for recording to finish...")

            wait_until_finished()

            final_info = get_remote_info()

            if final_info is None:
                continue

            final_mtime = final_info[0]

            number = get_next_number()
            filename = f"response_{number}.wav"

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

            last_mtime = final_mtime

            print()
            print("NEW AUDIO SAVED:")
            print(local_path)
            print()
            print("Waiting for another recording...")
            print()

        time.sleep(1)

    except KeyboardInterrupt:
        print("\nAudio watcher stopped.")
        break

    except Exception as e:
        print("Error:", e)
        time.sleep(2)