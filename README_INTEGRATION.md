# NAO Emotion Recognition — Integration Guide

**Last updated:** November 16, 2026  
**Status:** Local model and API integration checked; full physical NAO workflow validation pending.

## Overview

The physical NAO robot handles interaction, audio recording, and camera capture. A Windows PC runs FastAPI, Whisper Small, Qwen2.5-VL 3B, and ResMaskingNet.

## Quick Start

From the repository root on Windows, double-click `START_NAO.bat`, or run:

```powershell
.\START_NAO.ps1 -NaoIP YOUR_NAO_IP
```

The launcher checks connectivity and starts the NAO session coordinator `run_session.py`.

## Independent evaluation branches

- **Verbal:** WAV audio → Whisper transcription → Qwen emotion label → compare **only** to the displayed scenario's reference label → Correct / Incorrect / Unclear.
- **Facial:** NAO camera frame → ResMaskingNet → detected facial expression and confidence → report directly. No verbal response is required to process a saved frame.
- **Report:** Presents verbal correctness and facial observations in **separate sections**. There is **no verbal–facial comparison**, agreement metric, or mismatch score.

The verbal classifier uses Happy, Sad, Angry, Neutral and may output Unclear. Facial expression labels follow the configured ResMaskingNet model.

## Testing

```powershell
python -m unittest discover -s tests -v
```

Local testing has separately verified Whisper, Qwen and ResMaskingNet inference, plus the API audio and camera paths. Full physical end-to-end testing with NAO remains pending. Mock-based unit tests do not establish hardware readiness.

## Documentation

- `docs/CODE_WALKTHROUGH.md` — architecture and module responsibilities
- `docs/NAO_INTEGRATION.md` — integration, transfer and validation

## Notes

The project currently evaluates predefined technical scenarios, not children with ASD. Treat camera images and audio as sensitive test material. Older manual transfer and watcher utilities are not part of the active workflow.
