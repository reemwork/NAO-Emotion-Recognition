import sounddevice as sd
from scipy.io.wavfile import write
from datetime import datetime
import os

duration = 8
sample_rate = 16000

print("Recording... Speak now!")

audio = sd.rec(
    int(duration * sample_rate),
    samplerate=sample_rate,
    channels=1,
    dtype="int16"
)

sd.wait()

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

folder = "data/laptop_audio"
os.makedirs(folder, exist_ok=True)

filename = f"response_{timestamp}.wav"
file_path = os.path.join(folder, filename)

write(file_path, sample_rate, audio)

print("Recording finished!")
print(f"Saved as {file_path}")