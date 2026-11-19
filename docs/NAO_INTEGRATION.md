# NAO Emotion Recognition — Integration Guide

**Last Updated:** November 16, 2026
**Project:** NAO-Based Emotion Recognition System
**Status:** Local AI and backend integration validated; full physical NAO workflow testing pending.

---

## 1. Overview

The NAO-Based Emotion Recognition System uses the NAO V6 humanoid robot to conduct structured emotion-recognition activities.

The physical NAO robot handles participant interaction, audio recording, and camera capture. An external Windows PC performs AI processing and manages interaction sessions using FastAPI.

The system integrates:

- **NAO V6:** Human-robot interaction and data acquisition.
- **Whisper Small:** Speech-to-text transcription.
- **Qwen2.5-VL-3B:** Verbal emotion classification through Ollama.
- **ResMaskingNet:** Facial-expression classification.
- **FastAPI:** Backend communication, session management, evaluation, and reporting.

The current implementation focuses on technical prototype testing using predefined scenarios. Testing with children with Autism Spectrum Disorder (ASD) is not included in the current scope.

## 2. System Architecture

The system consists of two independent processing branches.

### Branch A — Verbal Emotion Evaluation

1. A predefined emotional image is displayed on an external screen.
2. NAO asks an open-ended question about the image.
3. NAO records the spoken response using its microphone.
4. The recorded audio is transferred to the external PC.
5. Whisper Small converts the audio into text.
6. Qwen2.5-VL-3B identifies the emotion described in the transcribed response.
7. The predicted emotion is compared **only** with the displayed image's predefined reference label.
8. The answer is evaluated as Correct, Incorrect, or Unclear.

The verbal emotion categories are:

- Happy
- Sad
- Angry
- Neutral

The classifier may return Unclear when the response cannot be confidently classified.

The language model uses the transcribed response for classification and does not receive the displayed emotional image as part of this classification task.

### Branch B — Facial Expression Analysis

1. NAO captures facial images using its camera.
2. The images are transferred to the external PC.
3. ResMaskingNet analyzes the captured facial expressions.
4. The predicted expression and confidence score are recorded.
5. The facial observations are included in the session report.

Facial-expression analysis is independent of verbal evaluation.

A facial image can be analyzed before a verbal response is submitted.

Facial predictions are not compared with verbal emotion classifications, are not used to determine answer correctness, and do not produce agreement or mismatch metrics.

Facial-expression labels follow the configured ResMaskingNet model.

## 3. Backend and Session Management

The FastAPI backend manages session initialization, predefined scenarios, data submission, AI evaluation, and report generation.

Important endpoints include:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Backend health check |
| POST | `/api/session/start` | Start a new interaction session |
| POST | `/api/session/end` | End an interaction session |
| GET | `/api/scenario/next` | Retrieve a predefined scenario |
| POST | `/api/scenario/start` | Activate a scenario |
| POST | `/api/scenario/complete` | Complete a scenario |
| POST | `/api/scenario/recovery` | Handle retry or skip operations |
| POST | `/api/response/submit` | Submit a verbal response |
| POST | `/api/audio/evaluate` | Transcribe and evaluate recorded audio |
| POST | `/api/camera/frame` | Receive an image |
| POST | `/api/camera/raw-frame` | Receive raw RGB camera data |
| POST | `/api/camera/session-frame` | Associate an image with a session |
| POST | `/api/facial/evaluate` | Evaluate a captured facial image |
| GET | `/api/session/{session_id}/report` | Retrieve the JSON session report |
| GET | `/api/session/{session_id}/report/view` | View the HTML session report |

The backend stores verbal results and facial observations separately.

## 4. One-Click NAO Startup (Windows)

The project includes a Windows startup workflow through:

- `START_NAO.bat`
- `START_NAO.ps1`

The startup script is designed to check robot connectivity, prepare the required local services, and launch the existing session coordinator.

### Prerequisites

Before starting a physical NAO session, ensure that:

- NAO V6 is powered on and available.
- The robot and development PC have network connectivity.
- The Python virtual environment is configured.
- Required Python dependencies are installed.
- Ollama is installed.
- The `qwen2.5vl:3b` model is available locally.
- SSH authentication and NAOqi connectivity are configured.
- The required scenarios and image assets exist.
- The robot is not being used by another developer.

### Starting a Session

From the repository root, double-click:

```text
START_NAO.bat
```

Alternatively, launch the PowerShell script manually:

```powershell
.\START_NAO.ps1 -NaoIP YOUR_NAO_IP
```

Replace `YOUR_NAO_IP` with the robot's actual IPv4 address.

### Startup Procedure

The PowerShell startup script performs the following operations:

1. Verifies the required Python executable and project files.
2. Checks the robot's network address.
3. Attempts to use a supplied or previously saved IP address.
4. Attempts to resolve `nao.local` when supported.
5. Requests manual IP entry if automatic discovery fails.
6. Checks whether Ollama is available.
7. Starts Ollama when necessary.
8. Verifies that `qwen2.5vl:3b` is installed.
9. Checks whether FastAPI is available at `127.0.0.1:8000`.
10. Starts FastAPI when necessary.
11. The launcher finishes after verifying NAO connectivity and preparing FastAPI and Ollama. It does not automatically start a session.
12. Saves the robot IP after the session coordinator exits successfully.

### Robot IP Detection

The script considers the following address sources:

1. Explicit `-NaoIP` parameter.
2. `NAO_IP` environment variable.
3. Saved address in `nao_connection.json`.
4. DNS resolution of `nao.local`.
5. Manual user input.

The script checks SSH port `22` to determine whether an address is reachable.

An accessible SSH port does not guarantee successful SSH authentication or NAOqi communication.

The script does not perform subnet-wide scanning.

### Saved Robot IP

The local configuration file is:

```text
nao_connection.json
```

Example:

```json
{
  "nao_ip": "192.168.1.100"
}
```

The address above is illustrative and is not the actual robot address.

The verified NAO IP address is saved after the startup checks and backend services are successfully prepared. The physical NAO interaction and data capture are triggered separately during integration.

The configuration should remain local rather than being committed to the repository.

### Startup Logs

Startup logs are stored under:

```text
data/startup_logs/
```

Log files include:

- `ollama.out.log`
- `ollama.err.log`
- `fastapi.out.log`
- `fastapi.err.log`

These files can help diagnose failures when starting Ollama or FastAPI.

### Startup Limitations

- The launcher does not guarantee that NAO is operational merely because SSH port 22 is reachable.
- Robot discovery may require manual IP entry.
- The correct Python environment and dependencies must already be configured.
- The full physical NAO interaction workflow has not yet been validated.
- The launcher does not establish that all scenarios, AI models, or robot actions will complete successfully.

## 5. Data Acquisition and Transfer

### Audio Acquisition

NAO records participant responses using its microphone.

The audio acquisition workflow is:

```text
NAO Microphone
    ↓
Audio Recording
    ↓
WAV File
    ↓
Robot-to-PC Transfer
    ↓
Whisper Small
    ↓
Transcribed Response
```

Audio recording and transfer were previously tested using the physical NAO V6.

### Camera Acquisition

NAO captures facial images through its camera.

Camera acquisition has been tested using both Virtual NAO and the physical robot.

The raw RGB camera workflow is:

```text
NAO Camera
    ↓
RGB Frame Capture
    ↓
HTTP Transfer
    ↓
FastAPI
    ↓
JPEG Image
    ↓
Session Storage
```

The physical robot has also been tested using `ALPhotoCapture` and image file transfer.

### Session Frame Processing

Captured facial images can be linked to an active session and scenario.

The backend records the captured image and can process it independently using ResMaskingNet.

The resulting observations are stored separately from verbal-response results.

Earlier manual transfer and file-watching utilities are retained as development history but are not part of the primary active session workflow.

## 6. AI Processing

### Speech-to-Text

**Model:** Whisper Small

Whisper converts recorded speech into a text transcript for verbal classification.

The transcription process runs on the external development PC.

### Verbal Emotion Classification

**Model:** Qwen2.5-VL-3B
**Runtime:** Ollama
**Input:** Transcribed verbal response

The model identifies the emotion described in the spoken answer.

The backend evaluates this prediction against the scenario's predefined reference label.

The evaluation output is:

- Correct
- Incorrect
- Unclear

### Facial Expression Classification

**Model:** ResMaskingNet
**Input:** Captured facial image

The model identifies the dominant facial expression and outputs a confidence score.

These observations are recorded in the facial-analysis section of the session report.

Facial observations do not influence verbal classification or response correctness.

## 7. Session Reporting

The system generates structured session reports in JSON and HTML formats.

The report contains two independent sections.

### Verbal Response Evaluation

Includes:

- Scenario reference label.
- Speech transcription.
- Predicted verbal emotion.
- Answer correctness.
- Verbal performance statistics.

### Facial Expression Observations

Includes:

- Captured facial images.
- Detected facial expressions.
- Confidence scores.
- Most frequently observed facial expression.
- Available capture and analysis metadata.

There is no comparison between the verbal and facial predictions.

The two branches contribute different information to the same report but remain analytically independent.

## 8. Testing and Validation

### Automated Unit Tests

Run the automated tests from the project root:

```powershell
python -m unittest discover -s tests -v
```

**Most recent verified result — November 16, 2026:**

- Total tests: 22
- Passed: 22
- Failed: 0

Some tests use mocked model failures to verify backend error handling.

Passing the unit tests does not demonstrate readiness of the physical NAO robot.

### Local Integration Testing

The following components have been successfully tested with real local model inference:

- Whisper Small audio transcription.
- Qwen2.5-VL-3B verbal emotion classification.
- ResMaskingNet facial-expression classification.
- FastAPI audio and camera evaluation endpoints.
- JSON and HTML session report generation.

A one-scenario local integration test verified:

1. Session creation.
2. Test-image submission.
3. Facial analysis before verbal submission.
4. Recording of facial observations.
5. Audio submission and transcription.
6. Verbal emotion classification.
7. Evaluation against the predefined reference label.
8. Independent reporting of verbal and facial results.
9. Scenario completion.
10. Session termination and report viewing.

The test used separately supplied audio and image files, not a fully synchronized physical NAO capture.

### Pending Physical Validation

The following tasks remain:

- Full end-to-end testing using NAO V6.
- Verification of audio and camera acquisition within the same live session.
- Testing the complete four-scenario workflow.
- Measuring end-to-end latency.
- Testing network and robot failure recovery.
- Validating repeated sessions for reliability.
- Reviewing privacy and data-retention safeguards.

## 9. Privacy and Data Handling

Audio recordings and captured images are processed locally on the development PC.

Locally captured audio and image directories are excluded from Git tracking to reduce the risk of committing sensitive data.

The implementation should be reviewed for secure storage, retention, access control, and deletion procedures before any future testing with participants.

Current testing is limited to predefined technical scenarios and does not involve children with ASD.

## 10. Related Documentation

- `README.md` — Project overview, architecture, model evaluation, and implementation progress.
- `PROGRESS.md` — Data acquisition, backend development, and contributor progress.
- `docs/CODE_WALKTHROUGH.md` — Detailed architecture, source code organization, and module responsibilities.
- `docs/NAO_INTEGRATION.md` — Integration setup, startup instructions, testing, and validation.

---

**Validation Status:** Local AI and backend integration tested successfully. Full end-to-end operation using the physical NAO robot remains pending.