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
    previous_size = None
    stable_count = 0

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