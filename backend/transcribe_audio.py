"""Legacy Whisper-small transcription helper for standalone NAO WAV files.

Loads the model once when imported. The current legacy path transcribes
Arabic; the session-based /api/audio/evaluate route uses English separately.
"""

import whisper
import glob
import os
import re

# Load once and reuse for multiple requests; this may allocate model RAM.
model = whisper.load_model("small")


def transcribe_audio(file_path):
    """Transcribe a saved WAV file with the shared Whisper-small model.

    This standalone/legacy helper currently sets language='ar' (Arabic).
    The session-aware /api/audio/evaluate endpoint separately uses English."""
    result = model.transcribe(
        file_path,
        language="ar"
    )

    return result["text"].strip()


if __name__ == "__main__":

    audio_folder = "data/nao_audio"

    audio_files = glob.glob(
        os.path.join(audio_folder, "response_*.wav")
    )

    if not audio_files:
        print("Error: No audio files found.")
        exit()


    def get_number(file_path):
        """Extract the numeric index from a response_<number>.wav filename."""
        filename = os.path.basename(file_path)

        match = re.search(
            r"response_(\d+)\.wav$",
            filename
        )

        if match:
            return int(match.group(1))

        return -1


    file_path = max(audio_files, key=get_number)

    print("Transcribing NAO audio...")
    print("Audio:", file_path)

    try:
        text = transcribe_audio(file_path)

        print("\n========== TRANSCRIPTION ==========")
        print(text)
        print("===================================")

        text_file = os.path.splitext(file_path)[0] + ".txt"

        with open(text_file, "w", encoding="utf-8") as f:
            f.write(text)

        print("\nTranscription saved to:", text_file)

    except Exception as e:
        print("Error:", e)