
"""Whisper Small transcription helper for NAO audio recordings.

The model is loaded once per Python process and reused for transcription.
Both standalone and session-based transcription use English.
"""

from pathlib import Path

import whisper


# Load Whisper Small once when this module is imported.
model = whisper.load_model("small")


def transcribe_audio(file_path):
    """Transcribe a WAV recording into English text."""
    result = model.transcribe(
        str(file_path),
        language="en",
        fp16=False
    )

    return result["text"].strip()


def get_latest_audio(folder):
    """Find the most recently modified NAO WAV recording."""
    audio_folder = Path(folder)

    audio_files = list(audio_folder.glob("response_*.wav"))

    if not audio_files:
        return None

    return max(
        audio_files,
        key=lambda file: file.stat().st_mtime_ns
    )


def main():
    """Transcribe the latest standalone NAO recording."""
    audio_folder = Path("data/nao_audio")
    audio_path = get_latest_audio(audio_folder)

    if audio_path is None:
        print("Error: No audio files found.")
        return

    print("Transcribing NAO audio...")
    print("Audio:", audio_path)

    try:
        text = transcribe_audio(audio_path)

        print("\n========== TRANSCRIPTION ==========")
        print(text)
        print("===================================")

        text_file = audio_path.with_suffix(".txt")
        text_file.write_text(text, encoding="utf-8")

        print("\nTranscription saved to:", text_file)

    except Exception as error:
        print("Error:", error)


if __name__ == "__main__":
    main()
