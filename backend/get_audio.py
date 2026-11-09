import os
import glob
import re
import subprocess

NAO_IP = "169.254.247.199"
REMOTE_AUDIO = "/home/nao/recordings/microphones/response.wav"
LOCAL_AUDIO = "data/nao_audio"

os.makedirs(LOCAL_AUDIO, exist_ok=True)

files = glob.glob(
    os.path.join(LOCAL_AUDIO, "response_*.wav")
)

numbers = []

for file in files:
    filename = os.path.basename(file)

    match = re.search(
        r"response_(\d+)\.wav$",
        filename
    )

    if match:
        numbers.append(int(match.group(1)))

next_number = max(numbers, default=0) + 1

filename = f"response_{next_number}.wav"

local_path = os.path.join(
    LOCAL_AUDIO,
    filename
)

print("Downloading NAO recording...")

subprocess.run(
    [
        "scp",
        f"nao@{NAO_IP}:{REMOTE_AUDIO}",
        local_path
    ],
    check=True
)

print("\nAudio saved:")
print(local_path)