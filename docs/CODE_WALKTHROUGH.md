# Developer Guide — NAO Emotion Recognition

**Project:** NAO Emotion Recognition and Training System
**Document Version:** 2.1
**Last Updated:** November 16, 2026
**Status:** Local Integration Validated — Physical NAO Testing Pending
**Project Type:** Computer Science Senior Project

---

## 1. Project Overview

The NAO Emotion Recognition system is a technical prototype designed to support structured emotion-recognition activities.

The NAO V6 humanoid robot presents predefined emotional scenarios, asks open-ended questions, records spoken responses, and captures facial images.

An external computer performs AI processing because NAO has limited computational resources.

The system has two independent processing branches.

### 1.1 Verbal Emotion Evaluation

1. NAO presents a predefined emotional scenario.
2. NAO records the spoken response.
3. Whisper Small transcribes the recorded audio into English text.
4. A locally hosted Qwen model classifies the emotion described in the response.
5. The predicted emotion is compared **only** with the displayed scenario's predefined reference label.
6. The system records the answer evaluation.

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

The verbal classifier does not use the captured facial image to determine the participant's answer.

### 1.2 Facial Expression Analysis

1. NAO captures a facial image.
2. The image is transferred to the external computer.
3. The configured ResMaskingNet adapter analyzes the facial expression.
4. The system records the detected expression and confidence score.
5. Results are stored as independent facial observations.

Facial analysis does not require a verbal response to be submitted first.

Facial-expression predictions are not used to determine verbal-answer correctness.

### 1.3 Independent Report Sections

The verbal branch evaluates the open-ended spoken description against the displayed scenario's reference emotion.

The facial branch independently detects and records visible expressions from captured camera frames.

The final report contains:

**Verbal Evaluation**
- Transcribed responses.
- Predicted verbal emotions.
- Predefined reference labels.
- Correctness evaluations.
- Verbal performance statistics.

**Facial Observations**
- Captured facial images.
- Detected expressions.
- Confidence scores.
- Most frequently observed expression.
- Capture and analysis metadata.

**Important:** The system does not compare verbal and facial predictions, calculate agreement or mismatch scores, or infer engagement from facial expressions.

Facial observations provide descriptive information for specialist review, not correctness or clinical measurements.

The current technical evaluation uses predefined scenarios and does not involve trials with children with Autism Spectrum Disorder (ASD).

---

## 2. System Architecture

### 2.1 Active Execution Workflow

```text
START_NAO.bat
    |
    v
START_NAO.ps1
    |
    +-- Verify NAO network and SSH connectivity
    +-- Check Ollama and Qwen model
    +-- Start or connect to FastAPI
    |
    v
run_session.py
    |
    +-- Start backend session
    +-- Retrieve predefined scenarios
    +-- Present emotional images
    +-- NAO speech interaction
    +-- Record WAV audio
    +-- Capture facial images
    +-- Transfer captured data
    |
    v
FastAPI Backend
    |
    +-- Facial Branch
    |      |
    |      +-- ResMaskingNet
    |      +-- Expression and confidence
    |      +-- Independent facial observations
    |
    +-- Verbal Branch
    |      |
    |      +-- Whisper Small
    |      +-- Qwen emotion classification
    |      +-- Compare with scenario reference label
    |      +-- Correct / Incorrect / Unclear
    |
    +-- Session Management
    +-- JSON Persistence
    +-- Report Generation
    |
    v
Session Report
    |
    +-- Verbal Evaluation
    +-- Facial Observations
```

The processing branches are independent.

In the current session coordinator, facial evaluation is requested before audio evaluation. This ordering is an implementation choice, not a dependency between the branches.

### 2.2 Processing Responsibilities

**NAO Robot**

- Speech output.
- Participant interaction.
- Audio recording.
- Camera image acquisition.
- Data capture during predefined scenarios.

**External Computer**

- Session coordination.
- Robot-to-PC file transfer.
- Speech transcription.
- Verbal emotion classification.
- Facial-expression inference.
- Session-state persistence.
- Report generation.

AI inference runs on the external computer rather than directly on NAO.

---

## 3. Source Code Structure

### 3.1 Startup and Session Coordination

| File | Responsibility |
|---|---|
| `START_NAO.bat` | Windows entry point for launching the workflow |
| `START_NAO.ps1` | Checks connectivity, prepares services, and starts the session coordinator |
| `run_session.py` | Coordinates the physical NAO session, data capture, file transfer, and backend API calls |
| `nao_connection.json` | Local configuration storing the previously successful NAO IP address |

The active physical-session entry point is `run_session.py`.

### 3.2 Backend Modules

| File | Responsibility |
|---|---|
| `backend/app.py` | FastAPI application initialization, router registration, and compatibility aliases |
| `backend/state.py` | Scenario configuration, in-memory state, and JSON persistence |
| `backend/sessions_api.py` | Session lifecycle, scenario management, retry/skip, and completion |
| `backend/responses.py` | Verbal response processing and correctness evaluation |
| `backend/audio.py` | Audio submission, speech transcription, and audio evaluation endpoints |
| `backend/transcribe_audio.py` | Legacy standalone Whisper transcription helper |
| `backend/emotion_classifier.py` | Qwen/Ollama classification requests and output validation |
| `backend/vision.py` | Camera uploads, image storage, and facial-observation endpoints |
| `backend/facial_classifier.py` | ResMaskingNet facial-expression inference adapter |
| `backend/reports.py` | JSON and HTML session reports |
| `backend/schemas.py` | Request schemas and input validation |

### 3.3 Testing and Historical Code

| File or Directory | Purpose |
|---|---|
| `tests/test_backend_workflow.py` | Backend and session coordinator unit tests |
| `tests/test_mvp_controller.py` | Offline MVP interaction workflow tests |
| `experiments/mllm/` | Earlier MLLM experiments |
| `archive/` | Historical experimental implementations and legacy components |

Experimental scripts are not automatically part of the active backend workflow.

### 3.4 Retired Components

The following standalone utilities have been removed from the active workflow:

- `backend/watch.py`
- `backend/nao_transfer.py`

Their responsibilities are now handled through the current session coordinator and backend APIs.

Older experimental workflows should not be used as alternative live-session coordinators.

The one-time camera integration patch script `apply_nao_camera_integration.py` has also been removed from the current working tree because its integration functionality is already present in the backend.

---

## 4. Data and Configuration

### 4.1 Scenario Configuration

**File:** `data/scenarios.json`

Defines predefined emotional scenarios and their associated information.

Scenario data includes:

- Scenario ID.
- Emotional image path.
- Predefined reference emotion label.

The four target emotions are:

- Happy
- Sad
- Angry
- Neutral

The reference label represents the expected answer for the displayed emotional image.

### 4.2 Model Evaluation Data

**File:** `data/mllm_test_cases.json`

Contains predefined test cases used to evaluate verbal emotion classification.

These test cases are separate from the actual physical NAO interaction workflow.

### 4.3 Session Storage

**File:** `data/sessions.json`

Stores session information, including:

- Session IDs.
- Session status.
- Scenario progress.
- Verbal responses.
- Transcription results.
- Predicted verbal emotions.
- Correctness evaluations.
- Audio and image references.
- Independent facial observations.

The implementation uses in-memory state backed by JSON persistence.

### 4.4 Robot Data Capture

**Directory:** `nao/data_capture/`

Contains robot-related capture materials and Choregraphe project files.

Review this directory before changing robot-side capture behavior or file paths.

### 4.5 Local Data Directories

The project uses local directories for recorded and processed data.

Examples include:

```text
data/
├── laptop_audio/
├── nao_audio/
├── nao_frames/
├── session_audio/
├── session_frames/
├── startup_logs/
└── sessions.json
```

Locally captured audio and images should remain excluded from version control.

---

## 5. Backend API Workflow

### 5.1 Session Execution

The current session coordinator uses the following workflow:

| Step | HTTP Method | Endpoint | Purpose |
|---|---|---|---|
| 1 | POST | `/api/session/start` | Create a new session |
| 2 | GET | `/api/scenario/next?index=0` | Retrieve predefined scenario information |
| 3 | POST | `/api/scenario/start` | Activate a scenario |
| 4 | POST | `/api/camera/session-frame` | Upload a captured facial image |
| 5 | POST | `/api/facial/evaluate` | Analyze and store independent facial observations |
| 6 | POST | `/api/audio/evaluate` | Transcribe and evaluate the spoken response |
| 7 | POST | `/api/scenario/complete` | Complete the scenario |
| 8 | POST | `/api/session/end` | End the session |
| 9 | GET | `/api/session/{session_id}/report` | Retrieve the JSON report |
| 10 | GET | `/api/session/{session_id}/report/view` | View the HTML report |

The facial evaluation request is made before the audio evaluation request in the current coordinator.

**Important:** Facial evaluation does not require the spoken response or its classification result.

Both branches store their outputs independently.

### 5.2 Recovery Operations

For missing or unusable responses, the system may use:

`POST /api/scenario/recovery`

This supports recovery operations such as retrying or skipping a scenario.

### 5.3 Camera APIs

The backend supports different camera input paths.

| Endpoint | Purpose |
|---|---|
| `/api/camera/frame` | Receive and save an uploaded image |
| `/api/camera/raw-frame` | Receive raw RGB data and convert it to an image |
| `/api/camera/session-frame` | Associate an image with a particular session and scenario |
| `/api/camera/target` | Bind incoming raw camera frames to an active session and scenario |
| `/api/facial/evaluate` | Run facial-expression inference |
| `/api/facial/result` | Store development facial observations |

The raw-frame route supports robot camera uploads, while the session-frame route supports explicit image association.

### 5.4 Upload Validation

Before uploading captured images or WAV audio, the session coordinator checks that:

- The session is active.
- The scenario ID matches the active scenario.
- Required input files are available.

The backend also validates the relevant session and scenario conditions.

These checks help prevent data from being associated with an incorrect session.

---

## 6. AI Models

### 6.1 Speech-to-Text

**Model:** Whisper Small
**Task:** Speech transcription
**Execution:** External computer

The active `/api/audio/evaluate` workflow transcribes English speech.

The legacy standalone transcription helper contains separate Arabic-language behavior and should not be confused with the active English workflow.

The transcript is passed to the verbal emotion classification component.

### 6.2 Verbal Emotion Classification

**Model:** Qwen2.5-VL-3B
**Runtime:** Ollama
**Model Identifier:** `qwen2.5vl:3b`
**Task:** Open-ended verbal emotion classification

The current classification request uses the transcribed spoken response.

The displayed emotional image is not provided to Qwen as part of the verbal classification input.

The predicted emotion is evaluated against the scenario's predefined reference label.

**Possible classification labels:**

- Happy
- Sad
- Angry
- Neutral
- Unclear

**Evaluation outcomes:**

- Correct.
- Incorrect.
- Unclear.

The verbal correctness evaluation depends only on the classified response and its predefined reference label.

### 6.3 Facial Expression Classification

**Model Adapter:** ResMaskingNet (RMN)
**Task:** Classification of visible facial expressions
**Execution:** External computer

The model analyzes captured images and returns:

- Dominant facial expression.
- Confidence score.

The facial classifier may support seven expression categories, while the verbal evaluation focuses on four target emotions.

Facial predictions are stored independently and are not used for verbal correctness evaluation.

### 6.4 Model Execution Boundaries

Whisper, Qwen, and ResMaskingNet run on the development computer.

NAO handles interaction and data capture.

The backend connects the processing modules and stores the resulting observations.

No verbal–facial emotion comparison is performed.

---

## 7. Running the Project

### 7.1 Physical NAO Session

From the repository root on Windows:

```powershell
.\START_NAO.bat
```

Alternatively:

```powershell
.\START_NAO.ps1 -NaoIP YOUR_NAO_IP
```

Replace `YOUR_NAO_IP` with the robot's actual IPv4 address.

The startup script:

1. Checks the Python environment and required files.
2. Detects or requests the NAO IP address.
3. Verifies SSH port connectivity.
4. Starts or connects to Ollama.
5. Checks that the Qwen model is available.
6. Starts or connects to FastAPI.
7. Launches `run_session.py`.
8. Saves the successfully used NAO IP when the coordinator exits successfully.

The launcher currently requires the backend to use port `8000`.

The complete physical NAO workflow has not yet been validated end-to-end.

### 7.2 Manual Backend Startup

For local development, start the backend independently:

```powershell
python -m uvicorn backend.app:app --reload
```

The backend is accessible at:

`http://127.0.0.1:8000/`

FastAPI Swagger documentation:

`http://127.0.0.1:8000/docs`

The `--reload` option is intended for development.

### 7.3 Ollama Requirements

Ensure Ollama is installed and the selected model is available.

To download the model:

```powershell
ollama pull qwen2.5vl:3b
```

To view installed models:

```powershell
ollama list
```

Ollama must be accessible to the backend during verbal emotion classification.

### 7.4 Startup Logs

Startup logs are written under:

```text
data/startup_logs/
```

Relevant logs include:

- `ollama.out.log`
- `ollama.err.log`
- `fastapi.out.log`
- `fastapi.err.log`

These logs can be inspected when startup fails.

---

## 8. Testing and Validation

### 8.1 Automated Unit Tests

From the repository root with the Python virtual environment active:

```powershell
python -m unittest discover -s tests -v
```

**Validation Date:** November 16, 2026

| Metric | Result |
|---|---|
| Total automated tests | 22 |
| Passed | 22 |
| Failed | 0 |
| Errors | 0 |

The automated suite uses mocked interfaces where appropriate.

### 8.2 Automated Test Coverage

The test suite covers:

- Session creation and lifecycle.
- Multiple scenarios within a session.
- Audio and image association.
- Speech-processing failure handling.
- Retry and skip behavior.
- Facial observation storage.
- Facial analysis independence from verbal submission.
- Exclusion of mock facial results from real-model statistics.
- Session report generation.
- Session and scenario upload validation.
- Rejection of uploads to inactive sessions.
- Offline MVP session execution.

### 8.3 Real Local Integration Test

In addition to automated unit tests, the backend was tested locally using real AI model inference.

**Validation Date:** November 16, 2026

The test used one predefined scenario with separate image and audio test files.

**Verified sequence:**

1. Started a new backend session.
2. Activated Scenario 1.
3. Uploaded a test image using the session-frame endpoint.
4. Requested facial analysis before submitting audio.
5. ResMaskingNet returned a real prediction.
6. Generated a report containing the facial observation without a verbal response.
7. Uploaded a WAV audio file.
8. Whisper Small transcribed the recorded speech.
9. Qwen2.5-VL-3B classified the described emotion.
10. The backend evaluated the verbal prediction against the reference label.
11. Verified that facial and verbal results appeared in separate report sections.
12. Completed the scenario.
13. Ended the session.
14. Viewed the generated HTML report.

**Facial Analysis Result**

- Model: ResMaskingNet.
- Predicted Expression: Angry.
- Confidence: 92.43%.
- Facial Observations: 1.

**Verbal Evaluation Result**

- Reference Label: Happy.
- Transcribed Response: "The girl looks sad because she is crying."
- Predicted Emotion: Sad.
- Evaluation: Incorrect.

**Session Result**

- Completed Scenarios: 1 of 4.
- Session Status: `ended_early`.
- Skipped Scenarios: 0.

The resulting JSON and HTML reports displayed the verbal evaluation and facial observations independently.

**Local Integration Test Result:** Passed.

The test image and audio were supplied separately and do not represent synchronized behavior from the same participant.

### 8.4 Testing Limitations

The unit tests and local integration test validate different aspects of the system.

**Automated unit tests** validate software behavior using controlled conditions and mocks.

**Local integration testing** demonstrates that the backend and real AI models can process test files successfully.

Neither establishes that the complete workflow works reliably on the physical NAO robot.

The following remain unverified as a complete physical workflow:

- End-to-end physical NAO connectivity.
- Live coordinated microphone and camera capture.
- Complete four-scenario execution.
- Continuous robot-to-PC communication.
- Real-time processing performance.
- Network failure recovery.
- Long-session reliability.

Full physical NAO validation is required before considering the integrated robotic workflow complete.

---

## 9. Important Technical Rules

### 9.1 Verbal Correctness Is Independent

Verbal correctness is determined by comparing the predicted verbal emotion with the displayed scenario's predefined reference label.

Facial-expression predictions must never modify verbal correctness.

### 9.2 Facial Analysis Does Not Depend on Audio

Facial images can be evaluated independently of spoken responses.

The backend must support facial observations even when no verbal response has been submitted.

### 9.3 Mock Observations

The endpoint `/api/facial/result` supports development observations marked with:

`source="mock"`

Mock observations must not be included in real facial-model statistics.

### 9.4 Facial Observations Are Descriptive

Facial predictions describe visible facial expressions.

They do not establish a person's internal emotional state and must not be treated as clinical or psychological assessments.

### 9.5 No Cross-Branch Comparison

The system does not:

- Compare verbal and facial emotion labels.
- Calculate agreement or mismatch metrics.
- Use facial predictions to determine verbal correctness.
- Infer engagement levels from facial predictions.

Both processing branches contribute their results to separate sections of the report.

### 9.6 Model Execution

Whisper Small, Qwen2.5-VL-3B, and ResMaskingNet execute on the connected computer.

NAO handles human-robot interaction and data capture.

### 9.7 State Management

The current implementation uses local files and in-memory session state backed by JSON persistence.

It is not designed as a multi-worker production database.

### 9.8 Data Association

Uploaded audio and facial images must be associated with the correct session and scenario.

Session validation should be maintained when modifying API routes or the session coordinator.

---

## 10. Developer Responsibilities

| Change Required | Primary Files |
|---|---|
| NAO session coordination | `run_session.py` |
| Windows startup | `START_NAO.bat`, `START_NAO.ps1` |
| Verbal emotion classification | `backend/emotion_classifier.py`, `backend/responses.py` |
| Speech transcription | `backend/audio.py`, `backend/transcribe_audio.py` |
| Camera frame ingestion | `backend/vision.py` |
| Facial model inference | `backend/facial_classifier.py` |
| Session lifecycle rules | `backend/sessions_api.py` |
| Session reporting | `backend/reports.py` |
| API schemas | `backend/schemas.py` |
| State persistence | `backend/state.py` |
| Automated testing | `tests/` |

Keep `backend/app.py` focused on application setup and router registration.

When changing session behavior or model integration:

1. Identify the responsible module.
2. Preserve the independent verbal and facial processing branches.
3. Update corresponding automated tests.
4. Run the test suite.
5. Update the relevant documentation.
6. Verify that existing API contracts remain consistent.

Do not reintroduce verbal–facial comparison logic.

---

## 11. Privacy and Evaluation Scope

The current system is a technical prototype.

Audio recordings, captured facial images, and AI results should remain within the authorized local development environment.

Before conducting real participant studies, additional safeguards are required, including:

- Appropriate consent and ethical approvals.
- Secure access to recorded data.
- Clear data-retention procedures.
- Authentication and authorization.
- Privacy and participant-protection controls.
- Validation of data storage and deletion behavior.

The current evaluation uses predefined technical scenarios.

The present implementation does not include actual trials involving children with ASD.

---

## 12. Development History

| Date | Development Activity | Status |
|---|---|---|
| October 2026 | Physical NAO audio recording, image capture, and local AI pipeline prototyping | Initial integration |
| November 16, 2026 | Integrated independent facial-expression evaluation into the backend session workflow | Verified locally |
| November 16, 2026 | Updated session reports to separate verbal correctness and facial observations | Verified locally |
| November 16, 2026 | Updated backend and transfer validation tests | 22 tests passed |
| November 16, 2026 | Performed a real local integration test using Whisper, Qwen, and ResMaskingNet | Passed |
| November 16, 2026 | Verified JSON and HTML reporting after completing and ending a test session | Passed |
| November 16, 2026 | Removed obsolete integration patch script from the current working tree | Local cleanup |
| November 16, 2026 | Updated developer documentation to reflect the current architecture | Documentation revision |

**Note:** Development dates summarize documented work. Git commit history remains the authoritative source for committed code changes.

---

## 13. Remaining Validation Work

Before considering the full physical system validated, the team must:

- [ ] Verify successful startup from `START_NAO.bat`.
- [ ] Confirm robot connectivity and NAOqi communication.
- [ ] Validate microphone recording during a complete physical session.
- [ ] Validate facial-image acquisition during the same session.
- [ ] Confirm audio and image transfer to the external computer.
- [ ] Verify Whisper and Qwen processing with real NAO recordings.
- [ ] Verify ResMaskingNet processing with real NAO camera frames.
- [ ] Confirm facial observations appear independently in reports.
- [ ] Test all four predefined scenarios in one session.
- [ ] Verify final session report contents.
- [ ] Measure processing latency.
- [ ] Test failures, retries, and recovery.
- [ ] Evaluate reliability over repeated sessions.
- [ ] Review privacy and data-retention safeguards.

**Current Validation Status:**

Local AI and backend integration have been tested successfully. The complete physical NAO V6 workflow remains pending.

---

**End of Developer Guide — Version 2.1**