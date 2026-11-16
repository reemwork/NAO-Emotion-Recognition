# Developer Guide — NAO Emotion Recognition

**Project:** NAO Emotion Recognition and Training System
**Document Version:** 2.0
**Last Updated:** November 16, 2026
**Status:** Refactoring and Integration Testing
**Project Type:** Computer Science Senior Project

---

## 1. Project Overview

The NAO Emotion Recognition system is a technical prototype designed to support structured emotion-recognition activities.

The NAO robot presents predefined emotional scenarios, asks questions, records spoken responses, and captures facial images.

The connected computer performs AI processing because NAO has limited computational resources.

The system produces two independent outputs:

### 1.1 Verbal Emotion Evaluation

1. NAO records the spoken response.
2. Whisper Small transcribes the audio into English text.
3. A locally hosted Qwen model classifies the described emotion.
4. The predicted emotion is compared with the scenario's predefined reference label.
5. The system records the answer evaluation.

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

`Unclear` indicates that the spoken response does not provide sufficient evidence for a reliable emotion classification.

### 1.2 Facial Expression Analysis

1. NAO captures a facial image.
2. The image is transferred to the computer.
3. The configured ResMaskingNet adapter analyzes the facial expression.
4. The system records the detected expression and confidence score.
5. Results are stored as independent facial observations.

Facial expressions do not determine whether a verbal response is correct.

### 1.3 Independent Report Sections

The verbal branch evaluates the open-ended spoken description against the displayed scenario's reference emotion. The facial branch independently detects and records expressions from NAO camera frames, including when no spoken answer has yet been saved.

The report contains separate verbal-performance and facial-observation sections. It does **not** compare verbal and facial labels and does not calculate agreement or mismatch scores. Facial observations are descriptive evidence for specialist review, not correctness or engagement measurements.

The current technical evaluation uses predefined scenarios and does not involve trials with children with Autism Spectrum Disorder (ASD).

---

## 2. System Architecture

The active execution workflow is:

```text
START_NAO.bat
      |
      v
START_NAO.ps1
      |
      +-- Verify NAO network and SSH connectivity
      +-- Check Ollama and the Qwen model
      +-- Start or connect to FastAPI
      |
      v
run_session.py
      |
      +-- Start backend session
      +-- Load emotional scenarios
      +-- Present scenario image
      +-- NAO speech interaction
      +-- Record WAV audio
      +-- Capture facial image
      +-- Transfer recordings via SCP
      |
      v
FastAPI Backend
      |
      +-- Whisper Small (Speech-to-Text)
      +-- Qwen (Text Emotion Classification)
      +-- ResMaskingNet (Facial Expression Analysis)
      +-- Session Management
      +-- Report Generation
      |
      v
Session Results (JSON / HTML)
```

### 2.1 Processing Responsibilities

**NAO Robot**
- Speech output
- Audio recording
- Camera image capture
- Interaction with the scenario

**External Computer**
- Session coordination
- File transfer
- Speech transcription
- Verbal emotion classification
- Facial-expression inference
- Data persistence
- Report generation

AI inference runs on the computer rather than directly on the robot.

---

## 3. Source Code Structure

### 3.1 Startup and Session Coordination

| File | Responsibility |
|---|---|
| `START_NAO.bat` | Windows entry point for launching the complete workflow |
| `START_NAO.ps1` | Checks connectivity, prepares services, and starts the session coordinator |
| `run_session.py` | Controls the physical NAO session, captures data, transfers files, and invokes backend APIs |
| `nao_connection.json` | Stores the previously successful NAO IP address |

### 3.2 Backend Modules

| File | Responsibility |
|---|---|
| `backend/app.py` | FastAPI application, router registration, and compatibility aliases |
| `backend/state.py` | Scenario configuration, in-memory state, and JSON persistence |
| `backend/sessions_api.py` | Session creation, scenario lifecycle, retry/skip, and session completion |
| `backend/responses.py` | Verbal response processing and correctness evaluation |
| `backend/audio.py` | Speech evaluation and audio API endpoints |
| `backend/transcribe_audio.py` | Legacy Whisper transcription helper |
| `backend/emotion_classifier.py` | Qwen/Ollama classification requests and output validation |
| `backend/vision.py` | Camera uploads, image storage, and facial-observation endpoints |
| `backend/facial_classifier.py` | Local ResMaskingNet inference adapter |
| `backend/reports.py` | JSON/HTML reports with independent verbal performance and facial observations |
| `backend/schemas.py` | Request payload types and validation |

### 3.3 Testing and Historical Code

| File or Directory | Purpose |
|---|---|
| `tests/test_backend_workflow.py` | Backend and physical-session coordinator unit tests |
| `tests/test_mvp_controller.py` | Offline MVP session workflow tests |
| `experiments/mllm/` | Earlier model experiments, not part of the active API pipeline |
| `archive/` | Historical experimental implementations and legacy components |

### 3.4 Retired Components

The following standalone utilities have been removed from the active workflow:

- `backend/watch.py`
- `backend/nao_transfer.py`

Their responsibilities are handled through the current session coordinator and backend APIs.

The active physical-session entry point is `run_session.py`.

Historical implementations should not be used as alternative live-session coordinators.

---

## 4. Data and Configuration

### 4.1 Scenario Configuration

**File:** `data/scenarios.json`

Defines the predefined scenarios and their associated information, including:

- Scenario ID
- Image path
- Reference emotion label

The four target scenario emotions are Happy, Sad, Angry, and Neutral.

### 4.2 Model Evaluation Data

**File:** `data/mllm_test_cases.json`

Contains predefined test cases for evaluating verbal emotion classification.

### 4.3 Session Storage

**File:** `data/sessions.json`

Stores session information, which can include:

- Session IDs and progress
- Scenario results
- Spoken responses
- Transcription and classification results
- Audio and image references
- Facial observations

### 4.4 Robot Data Capture

**Directory:** `nao/data_capture/`

Contains robot-related capture materials and Choregraphe project files.

Review this directory before changing robot-side file locations or capture behavior.

---

## 5. Backend API Workflow

The active session follows these API operations:

| Step | HTTP Method | Endpoint | Purpose |
|---|---|---|---|
| 1 | POST | `/api/session/start` | Create a session |
| 2 | GET | `/api/scenario/next?index=0` | Retrieve scenario information |
| 3 | POST | `/api/scenario/start` | Activate a scenario |
| 4 | POST | `/api/camera/session-frame` | Upload a captured image |
| 5 | POST | `/api/audio/evaluate` | Transcribe and evaluate the spoken response |
| 6 | POST | `/api/facial/evaluate` | Analyze the facial image |
| 7 | POST | `/api/scenario/complete` | Complete an answered scenario |
| 8 | POST | `/api/session/end` | End the session |
| 9 | GET | `/api/session/{session_id}/report` | Retrieve the JSON report |
| 10 | GET | `/api/session/{session_id}/report/view` | View the HTML report |

For missing or unusable responses, the system may use:

`POST /api/scenario/recovery`

This supports recovery behavior such as retrying or skipping a scenario.

### 5.1 Upload Validation

Before uploading a captured image or WAV file, the session coordinator checks that:

- The session is active.
- The scenario ID matches the currently active scenario.

This helps prevent files from being associated with the wrong scenario.

The backend must also enforce its own validation independently.

---

## 6. AI Models

### 6.1 Speech-to-Text

**Model:** Whisper Small
**Task:** Convert recorded speech into text
**Execution:** Local computer

The active `/api/audio/evaluate` workflow transcribes English speech.

The legacy transcription helper has separate Arabic-language behavior and must not be confused with the active English workflow.

### 6.2 Verbal Emotion Classification

**Model:** Qwen2.5-VL 3B
**Runtime:** Ollama
**Task:** Interpret an open-ended verbal emotion description

The current classification request uses transcribed text rather than the captured facial image.

The model output is evaluated against the predefined scenario reference label.

### 6.3 Facial Expression Classification

**Model Adapter:** ResMaskingNet (RMN)
**Task:** Classify visible facial expressions

The backend stores a predicted expression and confidence score.

The facial classifier may support seven expression categories, while the verbal evaluation uses four target emotion classes.

The approved model weights and preprocessing configuration should be verified before final deployment.

---

## 7. Running the Project

### 7.1 Physical NAO Session

From the repository root on Windows, launch:

```powershell
.\START_NAO.bat
```

Alternatively:

```powershell
.\START_NAO.ps1 -NaoIP YOUR_NAO_IP
```

The startup script:

1. Checks the Python environment and required files.
2. Detects or requests the NAO IP address.
3. Verifies SSH port connectivity.
4. Starts or connects to Ollama.
5. Checks that the Qwen model is available.
6. Starts or connects to FastAPI.
7. Launches `run_session.py`.
8. Saves the successfully used NAO IP when the coordinator exits successfully.

### 7.2 Manual Backend Startup

For development, start the backend independently:

```powershell
python -m uvicorn backend.app:app --reload
```

Swagger documentation:

`http://127.0.0.1:8000/docs`

The `--reload` option is intended for development.

---

## 8. Automated Testing

From the repository root with the Python virtual environment active:

```powershell
python -m unittest discover -s tests -v
```

### 8.1 Current Test Results

**Validation date:** November 16, 2026

| Metric | Result |
|---|---|
| Total automated tests | 22 |
| Passed | 22 |
| Failed | 0 |
| Errors | 0 |

The latest successful test run completed in approximately 0.33 seconds.

### 8.2 Tested Behavior

The automated suite covers:

- Session creation and lifecycle
- Multiple scenarios in one session
- Audio and image association
- Speech-processing failure handling
- Retry and skip behavior
- Facial observation storage
- Exclusion of mock facial results
- Session report generation
- Session/scenario upload validation
- Rejection of uploads to inactive sessions
- Offline MVP session execution

### 8.3 Testing Limitations

The unit tests use mocked interfaces for model inference and robot interaction.

Passing tests does not confirm:

- Physical NAO connectivity
- Real-time microphone and camera behavior
- Actual Whisper or Qwen inference
- Production ResMaskingNet inference
- Full end-to-end synchronization
- Hardware performance under continuous operation

A complete physical NAO session must be tested separately after integration changes.

---

## 9. Important Technical Rules

### 9.1 Verbal Correctness Is Independent

A correct verbal answer is determined from the classified verbal description and predefined reference label.

A facial-expression prediction must never change the verbal correctness result.

### 9.2 Mock Observations

The endpoint `/api/facial/result` can store development observations marked as `source="mock"`.

These observations are excluded from real facial-model statistics.

### 9.3 Facial Observations Are Descriptive

The system reports visible facial expressions, not verified internal emotions.

Facial results are not clinical or psychological assessments.

### 9.4 Model Execution

Whisper, Qwen, and ResMaskingNet execute on the connected computer.

NAO is responsible for interaction and data capture.

### 9.5 State Management

The current implementation uses local files and in-memory session state backed by JSON persistence.

It is not designed as a multi-worker production database.

---

## 10. Developer Responsibilities

| Change required | Primary files |
|---|---|
| NAO session coordination | `run_session.py` |
| Windows startup | `START_NAO.bat`, `START_NAO.ps1` |
| Verbal emotion classification | `backend/emotion_classifier.py`, `backend/responses.py` |
| Speech transcription | `backend/audio.py`, `backend/transcribe_audio.py` |
| Camera frame ingestion | `backend/vision.py` |
| Facial model inference | `backend/facial_classifier.py` |
| Session rules | `backend/sessions_api.py` |
| Reports and comparisons | `backend/reports.py` |
| API schemas | `backend/schemas.py` |
| Automated testing | `tests/` |

Keep `backend/app.py` focused on application setup and router registration.

When changing session behavior or model integration, update the corresponding tests and documentation.

---

## 11. Privacy and Evaluation Scope

The current system is a technical prototype.

Audio recordings, facial images, and model results should remain within the authorized local environment.

Before conducting real participant studies, additional safeguards are required, including:

- Appropriate consent and ethical approvals
- Secure access to recorded data
- Clear data-retention procedures
- Authentication and authorization
- Privacy and participant-protection controls

The present evaluation does not include actual trials involving children with ASD.

---

## 12. Development History

| Date | Development Activity | Status |
|---|---|---|
| October 2026 | Physical NAO audio recording, image capture, and local AI pipeline prototyping | Initial integration |
| November 16, 2026 | Integrated facial-expression evaluation into the session workflow and updated session reporting | Automated tests passed |
| November 16, 2026 | Updated transfer validation tests to target `run_session.py` | 22 tests passed |
| November 16, 2026 | Removed obsolete standalone watcher and transfer utilities from the active codebase | Local cleanup |
| November 16, 2026 | Updated developer documentation to reflect the unified execution workflow | Documentation revision |

**Note:** Dates in this history reflect the documented development period and current cleanup work. They are not a substitute for the authoritative Git commit timestamps.

---

## 13. Remaining Validation Work

Before considering the integrated physical system fully validated:

- Verify successful startup from `START_NAO.bat`.
- Confirm NAO audio and image capture in the updated workflow.
- Confirm real Whisper and Qwen inference.
- Verify ResMaskingNet model weights and preprocessing.
- Confirm facial predictions are included in final reports.
- Inspect report accuracy and stored session data.
- Test connection failures and recovery.
- Confirm privacy safeguards before any participant testing.

---

**End of Developer Guide — Version 2.0**
