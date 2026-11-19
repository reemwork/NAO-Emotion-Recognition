# NAO Emotion Recognition â€” Integration Guide

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

- **Verbal:** WAV audio â†’ Whisper transcription â†’ Qwen emotion label â†’ compare **only** to the displayed scenario's reference label â†’ Correct / Incorrect / Unclear.
- **Facial:** NAO camera frame â†’ ResMaskingNet â†’ detected facial expression and confidence â†’ report directly. No verbal response is required to process a saved frame.
- **Report:** Presents verbal correctness and facial observations in **separate sections**. There is **no verbalâ€“facial comparison**, agreement metric, or mismatch score.

The verbal classifier uses Happy, Sad, Angry, Neutral and may output Unclear. Facial expression labels follow the configured ResMaskingNet model.

## Testing

```powershell
python -m unittest discover -s tests -v
```

Local testing has separately verified Whisper, Qwen and ResMaskingNet inference, plus the API audio and camera paths. Full physical end-to-end testing with NAO remains pending. Mock-based unit tests do not establish hardware readiness.

## Documentation

- `docs/CODE_WALKTHROUGH.md` â€” architecture and module responsibilities
- `docs/NAO_INTEGRATION.md` â€” integration, transfer and validation

## Notes

The project currently evaluates predefined technical scenarios, not children with ASD. Treat camera images and audio as sensitive test material. Older manual transfer and watcher utilities are not part of the active workflow.


## One-Click NAO Startup (Windows)

The project provides a Windows startup workflow through `START_NAO.bat` and `START_NAO.ps1`.

### Prerequisites

Before starting a physical NAO session, ensure that:

- NAO V6 is powered on, available, and connected to the network.
- Python dependencies are installed in the project's virtual environment.
- Ollama is installed and the `qwen2.5vl:3b` model has been downloaded.
- SSH authentication and NAOqi connectivity have been configured.
- The required scenarios and image assets are available.
- The robot is not being used by another developer.

### Starting a Session

1. Open the project folder.
2. Double-click `START_NAO.bat`.
3. The startup script checks the robot's network address.
4. If the saved IP address is unavailable, the script attempts to resolve `nao.local`.
5. If neither works, enter the robot's current IPv4 address from Choregraphe.
6. The script checks and starts Ollama if necessary.
7. It verifies that the `qwen2.5vl:3b` model is available.
8. It checks and starts FastAPI on `127.0.0.1:8000` if necessary.
9. It launches `run_session.py` with the selected NAO IP address.
10. After a successful session process exit, the selected IP address is saved to `nao_connection.json` for future runs.

### Saved Robot IP

The local `nao_connection.json` file stores the previously used robot IP address.

Example:

```json
{
  "nao_ip": "192.168.1.100"
}
```

The address shown above is illustrative, not the actual robot IP.

The IP address is saved only after `run_session.py` exits successfully.

### Startup Logs

Startup logs are stored in:

```text
data/startup_logs/
```

Relevant files include:

- `ollama.out.log`
- `ollama.err.log`
- `fastapi.out.log`
- `fastapi.err.log`

### Important Notes

- The startup script does not scan the campus network.
- NAO might not be discoverable automatically if `nao.local` cannot be resolved.
- An open SSH port does not guarantee successful SSH authentication or NAOqi communication.
- Required software, dependencies, SSH keys, and robot configuration must already be installed.
- The startup workflow does not itself validate every step of a physical robot session.
- Complete end-to-end testing on physical NAO V6 is still pending.

**Validation Status:** Startup script reviewed; complete physical NAO session not yet verified.


## One-Click NAO Startup (Windows)

The project provides a Windows startup workflow through `START_NAO.bat` and `START_NAO.ps1`.

### Prerequisites

Before starting a physical NAO session, ensure that:

- NAO V6 is powered on, available, and connected to the network.
- Python dependencies are installed in the project's virtual environment.
- Ollama is installed and the `qwen2.5vl:3b` model has been downloaded.
- SSH authentication and NAOqi connectivity have been configured.
- The required scenarios and image assets are available.
- The robot is not being used by another developer.

### Starting a Session

1. Open the project folder.
2. Double-click `START_NAO.bat`.
3. The startup script checks the robot's network address.
4. If the saved IP address is unavailable, the script attempts to resolve `nao.local`.
5. If neither works, enter the robot's current IPv4 address from Choregraphe.
6. The script checks and starts Ollama if necessary.
7. It verifies that the `qwen2.5vl:3b` model is available.
8. It checks and starts FastAPI on `127.0.0.1:8000` if necessary.
9. It launches `run_session.py` with the selected NAO IP address.
10. After a successful session process exit, the selected IP address is saved to `nao_connection.json` for future runs.

### Saved Robot IP

The local `nao_connection.json` file stores the previously used robot IP address.

Example:

```json
{
  "nao_ip": "192.168.1.100"
}
```

The address shown above is illustrative, not the actual robot IP.

The IP address is saved only after `run_session.py` exits successfully.

### Startup Logs

Startup logs are stored in:

```text
data/startup_logs/
```

Relevant files include:

- `ollama.out.log`
- `ollama.err.log`
- `fastapi.out.log`
- `fastapi.err.log`

### Important Notes

- The startup script does not scan the campus network.
- NAO might not be discoverable automatically if `nao.local` cannot be resolved.
- An open SSH port does not guarantee successful SSH authentication or NAOqi communication.
- Required software, dependencies, SSH keys, and robot configuration must already be installed.
- The startup workflow does not itself validate every step of a physical robot session.
- Complete end-to-end testing on physical NAO V6 is still pending.

**Validation Status:** Startup script reviewed; complete physical NAO session not yet verified.
