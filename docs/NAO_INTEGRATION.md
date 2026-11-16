
# NAO Emotion Recognition — Integration Guide

**Last updated:** November 16, 2026
**Status:** Automated tests passed; physical end-to-end validation pending.

## Overview

The project uses a physical NAO robot for structured
emotion-recognition scenarios.

NAO handles speech interaction, audio recording, and camera capture.
A connected Windows PC runs the AI models and backend services.

## Quick Start

From the repository root on Windows, double-click:

`START_NAO.bat`

Alternatively, run:

```powershell
.\START_NAO.ps1 -NaoIP YOUR_NAO_IP
```

The launcher checks NAO SSH connectivity, prepares Ollama and
FastAPI, and starts `run_session.py`.

## Active Workflow

```text
START_NAO.bat
    |
    v
START_NAO.ps1
    |
    v
run_session.py
    |
    +-- NAO interaction
    +-- WAV recording
    +-- Camera capture
    +-- SCP transfer
    |
    v
FastAPI Backend
    |
    +-- Whisper Small: Speech-to-text
    +-- Qwen2.5-VL 3B: Verbal emotion classification
    +-- ResMaskingNet: Facial-expression classification
    +-- Session reports
```

## Requirements

- Physical NAO robot reachable over the network
- SSH authentication configured
- Python virtual environment with project dependencies
- Ollama with `qwen2.5vl:3b` available locally
- Whisper Small and the configured ResMaskingNet adapter
- Scenario images and `data/scenarios.json`

## Evaluation

The verbal classification uses four emotion classes:

- Happy
- Sad
- Angry
- Neutral

An additional `Unclear` outcome is used when verbal emotion
classification is unreliable.

Facial-expression analysis is independent of verbal correctness.

The session report presents verbal response accuracy and facial-expression observations in separate sections. There is no verbal–facial comparison or agreement/mismatch score. Facial analysis can run before a verbal response is submitted.

## Automated Tests

Run:

```powershell
python -m unittest discover -s tests -v
```

Latest recorded result on November 16, 2026:

**22 tests passed.**

The tests use mocked interfaces and do not verify the complete
physical robot and model pipeline.

## Documentation

For detailed information, read:

- `docs/CODE_WALKTHROUGH.md` — architecture and module responsibilities
- `docs/NAO_INTEGRATION.md` — capture, transfer, APIs, recovery, and validation

## Current Limitations

Physical end-to-end testing of the latest integrated workflow
is still required.

The configured facial model weights and preprocessing need
verification before final acceptance.

The current evaluation uses predefined technical scenarios,
not trials involving children with ASD.

## Legacy Components

The standalone watcher and manual transfer utilities have
been removed from the active workflow.

Use `run_session.py` as the physical NAO session coordinator.
