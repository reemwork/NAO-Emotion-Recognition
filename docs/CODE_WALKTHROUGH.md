# Developer Guide ط£آ¢أ¢â€ڑآ¬أ¢â‚¬â€Œ NAO Emotion Recognition

**Project:** NAO Emotion Recognition and Training System
**Document Version:** 2.2
**Last Updated:** November 19, 2026
**Status:** Backend and Local AI Integration Validated ط£آ¢أ¢â€ڑآ¬أ¢â‚¬â€Œ Physical NAO End-to-End Integration Pending
**Project Type:** Computer Science Senior Project

---

## 1. Project Overview

The NAO Emotion Recognition system is a technical prototype designed to support structured emotion-recognition activities.

The NAO V6 humanoid robot is intended to present predefined emotional scenarios, ask open-ended questions, record spoken responses, and capture facial images.

An external computer performs AI processing because NAO has limited computational resources.

The system includes two independent processing branches.

### 1.1 Verbal Emotion Evaluation

The intended workflow is:

1. NAO presents a predefined emotional scenario.
2. NAO records the spoken response.
3. The recorded audio is transferred to the external computer.
4. Whisper Small transcribes the audio into English text.
5. A locally hosted Qwen model classifies the emotion described in the response.
6. The predicted emotion is compared with the displayed scenario's predefined reference label.
7. The system records the answer evaluation.

**Supported verbal emotion labels:**
- Happy
- Sad
- Angry
- Neutral
- Unclear

**Evaluation outcomes:**
- Correct
- Incorrect
- Unclear

`Unclear` indicates insufficient evidence for reliable classification.

The verbal classifier does not use the captured facial images to determine answer correctness.

### 1.2 Facial Expression Analysis

The intended workflow is:

1. NAO captures facial images during the interaction.
2. The images are transferred to the external computer.
3. ResMaskingNet analyzes visible facial expressions.
4. The predicted expressions and confidence scores are recorded.
5. Results are stored as independent facial observations.

Facial analysis does not require a verbal response to be submitted first.

Facial predictions do not determine whether the spoken answer is correct.

### 1.3 Session Reports

The final report contains two independent sections.

**Verbal Evaluation**
- Transcribed responses.
- Predicted verbal emotions.
- Predefined reference labels.
- Correctness evaluations.
- Verbal performance statistics.

**Facial Observations**
- Captured facial-image references.
- Detected facial expressions.
- Confidence scores.
- Most frequently observed expression.
- Capture and analysis metadata.

The current backend stores verbal and facial results separately.

Facial predictions are descriptive observations and must not be interpreted as measurements of a participant's internal emotional state.

The current technical evaluation uses predefined scenarios and does not involve trials with children with Autism Spectrum Disorder (ASD).

---

## 2. System Architecture

### 2.1 Current Startup Workflow

```text
START_NAO.bat
    |
    v
START_NAO.ps1
    |
    +-- Check required Python environment
    |
    +-- Detect NAO IP address
    |
    +-- Verify NAO SSH connectivity
    |
    +-- Start or connect to Ollama
    |
    +-- Verify Qwen model availability
    |
    +-- Start or connect to FastAPI
    |
    +-- Save verified NAO IP configuration
    |
    v
Backend Services Ready
```

**Important:** The startup script does not automatically start a scenario, record audio, capture images, or execute a complete interaction session.

### 2.2 Physical NAO Data Capture

The file `nao_capture.py` is responsible for physical robot data capture.

Its intended responsibilities are:

1. Connect to the physical NAO robot through SSH.
2. Execute NAOqi audio and camera operations on the robot.
3. Record a WAV audio file.
4. Capture four camera frames during the recording interval.
5. Verify the generated files.
6. Transfer the captured files to the external computer using SCP.
7. Return the local audio and image paths to the calling component.

The capture function is:

```python
capture_from_nao(nao_ip, capture_id, output_dir)
```

The capture component does not:
- Select emotional scenarios.
- Display scenario images.
- Ask questions.
- Control conversational interaction.
- Classify verbal emotions.
- Classify facial expressions.
- Generate session reports.

The component must be triggered by the physical NAO interaction workflow once integration is completed.

### 2.3 Planned Integrated Workflow

```text
Physical NAO V6
    |
    +-- Scenario Interaction
    |       |
    |       +-- Present emotional image
    |       +-- Ask open-ended question
    |       +-- Manage participant interaction
    |
    +-- Audio and Camera Capture
            |
            +-- WAV recording
            +-- Four camera frames
            |
            v
       SSH / SCP Transfer
            |
            v
      External Computer
            |
            v
       FastAPI Backend
            |
            +-- Verbal Branch
            |       |
            |       +-- Whisper Small
            |       +-- Qwen Classification
            |       +-- Reference Label Comparison
            |       +-- Correct / Incorrect / Unclear
            |
            +-- Facial Branch
            |       |
            |       +-- ResMaskingNet
            |       +-- Facial Expression Prediction
            |       +-- Confidence Scores
            |       +-- Independent Observations
            |
            +-- Session Management
            +-- JSON Persistence
            +-- Report Generation
                    |
                    v
              Session Report
```

This represents the **target integration architecture**, not a fully validated physical implementation.

### 2.4 Processing Responsibilities

**NAO Robot**
- Human-robot interaction.
- Speech output.
- Audio recording.
- Camera image acquisition.
- Physical data capture.

**External Computer**
- Robot connectivity and file transfer.
- FastAPI backend execution.
- Speech transcription.
- Verbal emotion classification.
- Facial-expression classification.
- Session-state persistence.
- Report generation.

AI inference runs on the external computer rather than directly on NAO.

---

## 3. Source Code Structure

### 3.1 Startup and Physical Robot Capture

| File | Responsibility |
|---|---|
| `START_NAO.bat` | Windows entry point for startup |
| `START_NAO.ps1` | Checks NAO connectivity and prepares backend services |
| `nao_capture.py` | Records WAV audio and four camera frames on NAO and transfers them |
| `nao_connection.json` | Stores the verified NAO IP address |

The previous `run_session.py` coordinator has been removed from the active working tree.

There is currently no automatic full-session coordinator invoked by the startup script.

### 3.2 Backend Modules

| File or Module | Responsibility |
|---|---|
| `backend/app.py` | FastAPI application setup and router registration |
| `backend/state.py` | Scenario configuration, session state, and persistence |
| `backend/sessions_api.py` | Session lifecycle and scenario operations |
| `backend/responses.py` | Verbal response evaluation |
| `backend/audio.py` | Audio submission, transcription, and evaluation endpoints |
| `backend/transcribe_audio.py` | Standalone Whisper transcription helper |
| `backend/emotion_classifier.py` | Qwen/Ollama classification |
| `backend/vision/` | Camera ingestion and facial-observation APIs |
| `backend/facial_classifier.py` | ResMaskingNet inference adapter |
| `backend/reports.py` | Session report generation |
| `backend/schemas.py` | API request schemas and validation |

The old standalone `backend/vision.py` has been removed from the current working tree. The modular `backend/vision/` implementation is retained.

### 3.3 Testing and Historical Code

| File or Directory | Purpose |
|---|---|
| `tests/test_backend_workflow.py` | Backend workflow and facial-classifier tests |
| `experiments/` | Historical experimentation, where retained |
| `archive/` | Historical components, where retained |

The previous `tests/test_mvp_controller.py` and `scripts/run_mvp_session.py` have been removed.

Automated tests using mocks are development tools and are not alternative operational modes for the final physical NAO system.

### 3.4 Removed and Retired Components

The cleanup removes obsolete or superseded components, including:

- `run_session.py`
- `scripts/run_mvp_session.py`
- `tests/test_mvp_controller.py`
- `apply_nao_camera_integration.py`
- `backend/vision.py`
- `experiments/mllm/evaluate_mllm.py`
- `experiments/mllm/test_mllm.py`

Older standalone utilities such as `backend/watch.py` and `backend/nao_transfer.py` are also outside the intended active workflow.

Do not reintroduce a laptop-only session execution path as a replacement for physical NAO interaction.

---

## 4. Data and Configuration

### 4.1 Scenario Configuration

**File:** `data/scenarios.json`

Defines predefined scenarios, including:

- Scenario ID.
- Emotional image path.
- Predefined reference emotion label.

**Target emotions:**
- Happy
- Sad
- Angry
- Neutral

The reference label represents the expected answer for the displayed emotional image.

The physical interaction component must use the correct scenario and reference label during integration.

### 4.2 Model Evaluation Data

**File:** `data/mllm_test_cases.json`

Contains predefined test cases previously used for evaluating verbal emotion classification.

These cases are not part of physical NAO scenario execution.

### 4.3 Session Storage

**File:** `data/sessions.json`

The backend stores session information, including:

- Session IDs and status.
- Scenario progress.
- Verbal responses.
- Transcription results.
- Predicted verbal emotions.
- Correctness evaluations.
- Audio and image references.
- Independent facial observations.

The current implementation uses in-memory state backed by JSON persistence.

### 4.4 Robot Data Capture

**Active module:** `nao_capture.py`

This module records WAV audio and four camera frames
from the physical NAO robot and transfers them using SSH/SCP.

The previous Choregraphe data capture project has been
archived outside the active repository.

Physical interaction and capture coordination remain
pending integration.

**Main Python capture component:** `nao_capture.py`

The robot-side capture script uses NAOqi services to record audio and acquire camera images.

Before integration, ensure that audio and camera operations do not conflict with interaction components attempting to use the same NAO resources.

### 4.5 Local Data Directories

Local directories may include:

```text
data/
ط£آ¢أ¢â‚¬â€Œط¥â€œط£آ¢أ¢â‚¬â€Œأ¢â€ڑآ¬ط£آ¢أ¢â‚¬â€Œأ¢â€ڑآ¬ laptop_audio/
ط£آ¢أ¢â‚¬â€Œط¥â€œط£آ¢أ¢â‚¬â€Œأ¢â€ڑآ¬ط£آ¢أ¢â‚¬â€Œأ¢â€ڑآ¬ nao_audio/
ط£آ¢أ¢â‚¬â€Œط¥â€œط£آ¢أ¢â‚¬â€Œأ¢â€ڑآ¬ط£آ¢أ¢â‚¬â€Œأ¢â€ڑآ¬ nao_frames/
ط£آ¢أ¢â‚¬â€Œط¥â€œط£آ¢أ¢â‚¬â€Œأ¢â€ڑآ¬ط£آ¢أ¢â‚¬â€Œأ¢â€ڑآ¬ session_audio/
ط£آ¢أ¢â‚¬â€Œط¥â€œط£آ¢أ¢â‚¬â€Œأ¢â€ڑآ¬ط£آ¢أ¢â‚¬â€Œأ¢â€ڑآ¬ session_frames/
ط£آ¢أ¢â‚¬â€Œط¥â€œط£آ¢أ¢â‚¬â€Œأ¢â€ڑآ¬ط£آ¢أ¢â‚¬â€Œأ¢â€ڑآ¬ startup_logs/
ط£آ¢أ¢â‚¬â€Œأ¢â‚¬â€Œط£آ¢أ¢â‚¬â€Œأ¢â€ڑآ¬ط£آ¢أ¢â‚¬â€Œأ¢â€ڑآ¬ sessions.json
```

Some directories contain historical development artifacts and are not necessarily active data sources.

Real recordings and images should be stored locally and excluded from version control where appropriate.

---

## 5. Backend API Workflow

### 5.1 Session Endpoints

The backend provides APIs for managing sessions and processing captured data.

| HTTP Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/session/start` | Create a session |
| GET | `/api/scenario/next?index=0` | Retrieve scenario information |
| POST | `/api/scenario/start` | Activate a scenario |
| POST | `/api/camera/session-frame` | Upload a session image |
| POST | `/api/facial/evaluate` | Evaluate facial expressions |
| POST | `/api/audio/evaluate` | Transcribe and evaluate recorded audio |
| POST | `/api/scenario/complete` | Complete a scenario |
| POST | `/api/session/end` | End a session |
| GET | `/api/session/{session_id}/report` | Retrieve JSON report |
| GET | `/api/session/{session_id}/report/view` | View HTML report |

These endpoints remain backend capabilities.

Their existence does not mean the current startup script automatically executes the entire workflow.

### 5.2 Recovery Operations

The endpoint:

`POST /api/scenario/recovery`

Supports operations such as retrying or skipping a scenario.

Recovery decisions belong to the interaction and session-management workflow.

### 5.3 Camera APIs

| Endpoint | Purpose |
|---|---|
| `/api/camera/frame` | Receive an uploaded camera image |
| `/api/camera/raw-frame` | Receive raw camera data |
| `/api/camera/session-frame` | Associate an image with a session and scenario |
| `/api/camera/target` | Associate incoming raw frames with a target session/scenario |
| `/api/facial/evaluate` | Run facial-expression inference |
| `/api/facial/result` | Store development facial observations |

The session-frame route supports explicit image association.

### 5.4 Data Association and Validation

Before associating captured data with a scenario, the integrated workflow must verify:

- The session is active.
- The scenario ID is correct.
- Audio and image files exist.
- The uploaded files belong to the intended capture.
- Required backend endpoints are available.

The backend also enforces relevant session and scenario conditions.

The removed `run_session.py` previously contained additional transfer and upload coordination logic. Equivalent validation and data association must be established during future integration.

---

## 6. AI Models

### 6.1 Speech-to-Text

**Model:** Whisper Small
**Task:** Speech transcription
**Execution:** External computer

The active backend audio-evaluation workflow processes English speech.

Whisper converts recorded audio into text for verbal emotion classification.

### 6.2 Verbal Emotion Classification

**Model:** Qwen2.5-VL-3B
**Runtime:** Ollama
**Model Identifier:** `qwen2.5vl:3b`

The current verbal classification workflow uses the transcribed spoken response as input.

The displayed image is not currently provided to Qwen for verbal classification.

Possible outputs:

- Happy
- Sad
- Angry
- Neutral
- Unclear

The result is compared with the displayed scenario's predefined reference label to determine:

- Correct
- Incorrect
- Unclear

### 6.3 Facial Expression Classification

**Model Adapter:** ResMaskingNet (RMN)
**Task:** Classification of visible facial expressions
**Execution:** External computer

The model analyzes camera images and returns:

- Dominant facial expression.
- Confidence score.

The facial model may support seven expression categories, while the verbal evaluation uses four target emotion classes.

Facial results remain independent from verbal correctness.

### 6.4 Model Execution Boundaries

Whisper, Qwen, and ResMaskingNet run on the connected external computer.

The physical NAO robot handles interaction and data capture.

The backend stores and processes the resulting observations.

The currently documented backend does not calculate verbalط£آ¢أ¢â€ڑآ¬أ¢â‚¬إ“facial agreement or mismatch metrics.

---

## 7. Running the Project

### 7.1 Preparing the Physical NAO Environment

From the repository root on Windows:

```powershell
.\START_NAO.bat
```

Alternatively:

```powershell
.\START_NAO.ps1 -NaoIP YOUR_NAO_IP
```

Replace `YOUR_NAO_IP` with the robot's IPv4 address.

The startup script:

1. Checks the Python environment and required backend files.
2. Detects or requests the NAO IP address.
3. Verifies SSH connectivity.
4. Starts or connects to Ollama.
5. Verifies the required Qwen model.
6. Starts or connects to FastAPI.
7. Saves the verified NAO IP configuration.

**The startup script does not automatically start a physical interaction session.**

The current backend uses port `8000`.

### 7.2 Physical Capture Component

**File:** `nao_capture.py`

The capture function is intended to be invoked after an interaction event from the physical NAO workflow.

It requires:

- A reachable physical NAO robot.
- Working SSH access.
- Access to NAOqi audio and camera services.
- An output directory on the external computer.

The function captures a WAV recording and four camera frames, then transfers them using SCP.

This component is not a standalone scenario controller.

The complete interaction-to-capture integration has not yet been validated.

### 7.3 Manual Backend Startup

For backend development or diagnostics:

```powershell
python -m uvicorn backend.app:app --reload
```

Backend address:

`http://127.0.0.1:8000/`

FastAPI API documentation:

`http://127.0.0.1:8000/docs`

The `--reload` option is intended for development.

Manual backend startup does not replace the physical NAO workflow.

### 7.4 Ollama Requirements

Ensure Ollama is installed and the model is available.

To download the model:

```powershell
ollama pull qwen2.5vl:3b
```

To inspect installed models:

```powershell
ollama list
```

Ollama must be accessible to the backend during verbal emotion classification.

### 7.5 Startup Logs

Startup logs are stored under:

```text
data/startup_logs/
```

Relevant logs include:

- `ollama.out.log`
- `ollama.err.log`
- `fastapi.out.log`
- `fastapi.err.log`

These logs can be inspected if service startup fails.

---

## 8. Testing and Validation

### 8.1 Previous Automated Validation

**Historical Validation Date:** November 16, 2026

The previous automated test suite reported:

| Metric | Historical Result |
|---|---|
| Total automated tests | 22 |
| Passed | 22 |
| Failed | 0 |
| Errors | 0 |

These results describe the earlier implementation, before the November 19 cleanup.

They must not be interpreted as validation of the newly modified capture component or current test suite.

### 8.2 Backend Test Coverage

The backend tests cover behavior such as:

- Session creation and lifecycle.
- Multiple scenarios within a session.
- Audio and image association.
- Speech-processing failure handling.
- Retry and skip behavior.
- Facial observation storage.
- Facial analysis independent of verbal submission.
- Report generation.
- Facial classifier output normalization.
- API route compatibility.

Tests depending on the removed session coordinator are being removed or updated.

Backend tests use controlled inputs and mocked model interfaces where appropriate.

They do not simulate a complete physical NAO session for operational use.

### 8.3 Previous Local AI Integration Test

**Historical Validation Date:** November 16, 2026

A local backend integration test previously demonstrated that:

1. A backend session could be started.
2. A predefined scenario could be activated.
3. A facial image could be uploaded.
4. ResMaskingNet could analyze the uploaded image.
5. A WAV file could be submitted.
6. Whisper Small could transcribe the audio.
7. Qwen could classify the verbal emotion.
8. The backend could compare the prediction with the reference label.
9. JSON and HTML reports could be generated.

**Recorded facial result:**
- Model: ResMaskingNet
- Predicted Expression: Angry
- Confidence: 92.43%

**Recorded verbal result:**
- Reference Label: Happy
- Transcribed Response: "The girl looks sad because she is crying."
- Predicted Emotion: Sad
- Evaluation: Incorrect

The previous local test passed.

However, the image and audio were supplied separately and did not demonstrate synchronized physical NAO interaction.

### 8.4 Physical Validation Limitations

The complete physical NAO workflow remains unverified.

Outstanding validation includes:

- Full robot connectivity and NAOqi operations.
- Coordinated microphone and camera capture.
- Correct capture timing.
- Transfer of all captured files.
- Correct association of audio and frames with each scenario.
- Integration with the interaction component.
- Full four-scenario execution.
- Continuous communication between NAO and the external computer.
- Recovery from network and processing failures.
- End-to-end report generation.
- Repeated-session reliability.

Successful backend inference alone does not establish complete physical system functionality.

---

## 9. Important Technical Rules

### 9.1 Physical NAO Is Required

The operational workflow must use a real NAO robot for interaction and data capture.

Do not introduce a laptop-only scenario execution mode as a substitute for the robot.

The external computer remains necessary for AI processing and backend services.

### 9.2 Separate Capture From Interaction

`nao_capture.py` handles data capture and transfer.

Scenario presentation, questioning, interaction timing, and conversational flow are separate responsibilities.

Integration must coordinate these components without duplicating their functions.

### 9.3 Verbal Correctness Is Independent

Verbal correctness is determined by comparing the classified spoken response with the scenario's predefined reference label.

Facial-expression predictions must not modify verbal correctness.

### 9.4 Facial Analysis Does Not Depend on Audio

Facial images can be analyzed independently of spoken responses.

The backend should support facial observations without requiring prior verbal classification.

### 9.5 Mock Observations

The backend development endpoint `/api/facial/result` may store observations marked:

`source="mock"`

Mock observations must not be included in real facial-model statistics.

Mock data is used only for software validation, not as a substitute for real NAO capture in the operational system.

### 9.6 Facial Observations Are Descriptive

Facial predictions describe visible facial expressions.

They do not establish a person's internal emotional state and are not clinical or psychological assessments.

### 9.7 Model Execution

Whisper Small, Qwen2.5-VL-3B, and ResMaskingNet run on the connected external computer.

NAO performs interaction and data capture.

### 9.8 Data Association

Each recording and camera frame must be associated with the correct session and scenario.

Capture identifiers, filenames, and backend session identifiers must remain consistent.

### 9.9 Resource Coordination

Avoid competing microphone recordings or simultaneous access that conflicts with the NAO interaction component.

Capture timing and ownership of robot audio/camera resources must be agreed upon during integration.

---

## 10. Developer Responsibilities

| Change Required | Primary Files or Components |
|---|---|
| Physical NAO data capture | `nao_capture.py` |
| Windows startup | `START_NAO.bat`, `START_NAO.ps1` |
| NAO interaction and scenario presentation | Separate interaction component, pending integration |
| Verbal emotion classification | `backend/emotion_classifier.py`, `backend/responses.py` |
| Speech transcription | `backend/audio.py`, `backend/transcribe_audio.py` |
| Camera frame ingestion | `backend/vision/` |
| Facial model inference | `backend/facial_classifier.py` |
| Session lifecycle | `backend/sessions_api.py` |
| Session reporting | `backend/reports.py` |
| API schemas | `backend/schemas.py` |
| State persistence | `backend/state.py` |
| Backend testing | `tests/` |

Keep `backend/app.py` focused on application initialization and router registration.

When changing integration behavior:

1. Identify the responsible component.
2. Preserve the independence of verbal and facial processing.
3. Maintain correct session and scenario identifiers.
4. Prevent conflicting NAO microphone and camera operations.
5. Update relevant tests.
6. Verify API compatibility.
7. Update the documentation.
8. Validate with the physical robot before claiming end-to-end completion.

---

## 11. Privacy and Evaluation Scope

The current system is a technical prototype.

Audio recordings, captured facial images, and AI-generated results should remain within the authorized local development environment.

Before real participant studies, additional safeguards are required, including:

- Appropriate consent and ethical approval.
- Secure access to recordings and captured images.
- Clear data-retention procedures.
- Authentication and authorization.
- Privacy and participant-protection controls.
- Validation of data storage and deletion behavior.

The current evaluation uses predefined technical scenarios.

The present project scope does not include actual trials involving children with ASD.

---

## 12. Development History

| Date | Development Activity | Status |
|---|---|---|
| October 2026 | Physical NAO audio recording and image capture prototyping | Initial verification |
| November 16, 2026 | Independent facial-expression evaluation integrated into backend | Locally validated |
| November 16, 2026 | Verbal and facial sections organized in reports | Locally validated |
| November 16, 2026 | Automated backend validation | 22 historical tests passed |
| November 16, 2026 | Local integration with Whisper, Qwen, and ResMaskingNet | Passed |
| November 19, 2026 | Removal of obsolete offline MVP coordination scripts | Local cleanup |
| November 19, 2026 | Separation of physical NAO capture into `nao_capture.py` | Implementation updated |
| November 19, 2026 | Startup script no longer launches the removed session coordinator | Implementation updated |
| November 19, 2026 | Developer documentation updated to reflect physical-NAO integration architecture | Documentation updated |

Development dates summarize documented activities.

Git history remains the authoritative source for committed code changes.

---

## 13. Remaining Integration and Validation Work

Before considering the full system validated:

- [ ] Verify the updated startup script.
- [ ] Confirm physical NAO SSH and NAOqi connectivity.
- [ ] Validate `nao_capture.py` with the real robot.
- [ ] Confirm one WAV recording is captured correctly.
- [ ] Confirm four camera frames are captured correctly.
- [ ] Confirm successful audio and image transfer through SCP.
- [ ] Coordinate capture timing with the interaction component.
- [ ] Connect physical interaction events to capture operations.
- [ ] Associate captured files with the correct backend session and scenario.
- [ ] Verify Whisper processing of real NAO recordings.
- [ ] Verify Qwen evaluation of transcribed responses.
- [ ] Verify ResMaskingNet processing of real NAO frames.
- [ ] Confirm independent verbal and facial results in reports.
- [ ] Validate all four predefined scenarios in one physical session.
- [ ] Test recording, network, and processing failure recovery.
- [ ] Measure end-to-end processing latency.
- [ ] Evaluate reliability over repeated sessions.
- [ ] Review privacy and data-retention safeguards.

**Current Validation Status:**

Previous local backend and AI integration tests were successful.

The physical NAO capture component has been separated from the removed session coordinator.

Full interaction integration, coordinated data transfer, and complete physical NAO end-to-end validation remain pending.

---

**End of Developer Guide ط£آ¢أ¢â€ڑآ¬أ¢â‚¬â€Œ Version 2.2**