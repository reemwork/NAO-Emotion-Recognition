# Reem — NAO Data Acquisition & Backend Progress

**Project:** NAO-Based Emotion Recognition System
**University:** University of Jeddah
**Academic Year:** 2026–2027
**Last Updated:** November 16, 2026

---

## 1. My Responsibilities

My primary responsibility is developing and testing the data acquisition and communication pipeline between the NAO V6 humanoid robot and the PC-based emotion recognition system.

My work focuses on:

- NAO microphone and camera integration.
- Audio recording and image acquisition.
- Data transfer and file organization.
- FastAPI backend development and session management.
- Testing and troubleshooting robot-to-PC communication.
- Integrating acquired data with downstream AI processing components.
- Supporting system integration, testing, and reporting.

## 2. Completed Work

### Audio Acquisition

- [x] Created the NAO Data Capture project in Choregraphe.
- [x] Developed the `Capture_Audio` component.
- [x] Implemented recording using `ALAudioRecorder`.
- [x] Configured an approximately 8-second response recording window.
- [x] Implemented recording start and stop logic.
- [x] Tested the recording workflow with Virtual NAO.
- [x] Handled Virtual NAO microphone limitations.
- [x] Tested local microphone recording.
- [x] Successfully recorded audio using the physical NAO V6 microphone.
- [x] Transferred recorded WAV files from NAO to the PC.
- [x] Organized recordings using sequential filenames.

### Camera Acquisition

- [x] Developed the `Capture_Camera` component in Choregraphe.
- [x] Accessed `ALVideoDevice` using Virtual NAO.
- [x] Captured 320 × 240 RGB frames.
- [x] Implemented raw RGB frame transfer to FastAPI.
- [x] Converted received RGB data into JPEG images.
- [x] Saved captured images in `data/nao_frames/`.
- [x] Tested the Virtual NAO camera-to-backend workflow.
- [x] Tested camera acquisition using the laptop camera and OpenCV.
- [x] Successfully captured images using the physical NAO V6 camera.
- [x] Tested physical robot image acquisition using `ALPhotoCapture`.

### Robot Communication & File Transfer

- [x] Established SSH communication with the physical NAO robot.
- [x] Configured SCP file transfers between NAO and the PC.
- [x] Set up passwordless SSH authentication.
- [x] Successfully retrieved recorded audio and captured images.
- [x] Developed file-monitoring and sequential naming scripts to support automated data transfer.

### Backend Development

Developed and integrated a Python backend using FastAPI to manage interaction sessions, receive data, evaluate verbal responses, and record independent facial-expression observations.

Implemented endpoints include:

- [x] `GET /` — Backend health check.
- [x] `POST /api/session/start` — Initialize a session.
- [x] `POST /api/session/end` — End an interaction session.
- [x] `GET /api/scenario/next` — Retrieve predefined scenarios.
- [x] `POST /api/scenario/start` — Start a scenario.
- [x] `POST /api/scenario/complete` — Complete a scenario.
- [x] `POST /api/scenario/recovery` — Handle retry and skip operations.
- [x] `POST /api/response/submit` — Submit a verbal response.
- [x] `POST /api/audio/evaluate` — Transcribe and evaluate recorded audio.
- [x] `POST /api/camera/frame` — Receive and save images.
- [x] `POST /api/camera/raw-frame` — Receive raw RGB camera data.
- [x] `POST /api/camera/session-frame` — Associate a captured frame with a session.
- [x] `POST /api/facial/evaluate` — Analyze facial expressions independently.
- [x] `GET /api/session/{session_id}/report` — Generate a structured JSON report.
- [x] `GET /api/session/{session_id}/report/view` — Display an HTML report.

The backend now supports persistent session records, scenario management, verbal-answer evaluation, independent facial-expression analysis, and automated session reporting.

These features have been validated through local integration testing.

### Data Management & Privacy

- [x] Organized separate folders for recorded audio and captured images.
- [x] Added locally recorded audio directories to `.gitignore`.
- [x] Added captured-image directories to `.gitignore`.
- [x] Excluded local test recordings and captured images from Git tracking.
- [x] Implemented session-specific storage for uploaded audio and camera frames.

Captured audio and images are intended to remain on the local development computer. Additional privacy and data-retention safeguards require further review before use with real participants.

## 3. Verified Data Acquisition Workflows

### Physical NAO Audio Workflow

NAO Microphone → Audio Recording → WAV File → SSH/SCP → PC Storage

**Status:** Successfully tested with the physical NAO V6.

### Physical NAO Image Acquisition

NAO Camera → ALPhotoCapture → Image File → PC Transfer

**Status:** Physical robot image capture and file retrieval tested successfully.

### Virtual NAO Camera-to-Backend Workflow

Virtual NAO Camera → ALVideoDevice → Raw RGB Frame → HTTP → FastAPI → JPEG Conversion → Local Storage

**Status:** Successfully tested.

### Laptop Camera-to-Backend Workflow

Laptop Camera → OpenCV → FastAPI → Local Storage

**Status:** Successfully tested.

These acquisition workflows have been tested separately. A complete physical NAO interaction integrating audio, camera capture, AI evaluation, and reporting remains to be validated.

## 4. AI Processing and Local Integration

### Speech-to-Text — Whisper Small

- [x] Installed and configured Whisper Small locally.
- [x] Successfully transcribed an English audio recording.
- [x] Integrated Whisper with the FastAPI audio evaluation endpoint.
- [x] Verified transcription results using real model inference.

**Verified transcription example:**

"The girl looks sad because she is crying."

### Verbal Emotion Classification — Qwen2.5-VL-3B

- [x] Configured Qwen2.5-VL-3B locally using Ollama.
- [x] Tested text emotion classification using real model inference.
- [x] Integrated verbal classification with the FastAPI backend.
- [x] Compared the predicted verbal emotion with the scenario's predefined reference label.
- [x] Verified response correctness evaluation.

**Local test example:**

- Reference Label: Happy
- Transcribed Response: "The girl looks sad because she is crying."
- Predicted Emotion: Sad
- Answer Evaluation: Incorrect

The classification result was evaluated against the reference label of the displayed scenario image.

### Facial Expression Classification — ResMaskingNet

- [x] Installed and configured ResMaskingNet locally.
- [x] Tested facial-expression recognition using real model inference.
- [x] Integrated facial analysis with the FastAPI backend.
- [x] Successfully analyzed a captured test image before submitting any verbal response.
- [x] Recorded detected facial expressions and confidence scores independently.
- [x] Verified that facial observations are preserved after submitting an audio response.

**Local test example:**

- Detected Expression: Angry
- Confidence: 92.43%
- Model: ResMaskingNet
- Facial Observations: 1

Facial-expression analysis is independent of verbal-response evaluation.

Facial expressions are recorded directly in the session report and are not compared against verbal classifications or used to determine answer correctness.

### Session Reporting

- [x] Implemented structured JSON session reports.
- [x] Implemented HTML session reports with captured images.
- [x] Included verbal classification and answer correctness.
- [x] Included facial-expression observations and confidence scores.
- [x] Separated verbal performance and facial observations into independent report sections.
- [x] Verified that facial analysis can be reported without a submitted verbal response.
- [x] Verified report contents after both audio and facial results were available.
- [x] Verified that report data remained accessible after ending a session.

**Report Structure:**

**Section 1 — Verbal Response Evaluation**
- Reference emotion label.
- Transcribed spoken response.
- Predicted verbal emotion.
- Answer evaluation.
- Session-level verbal performance statistics.

**Section 2 — Facial Expression Observations**
- Captured facial images.
- Detected facial expressions.
- Model confidence scores.
- Most frequently observed facial expression.
- Frame analysis information.

No verbal–facial comparison is included in the report.

## 5. Testing and Validation

### Automated Testing

- [x] Executed the automated Python unit test suite.
- [x] Passed all 22 unit tests on November 16, 2026.
- [x] Verified scenario and session management.
- [x] Verified audio processing error handling using mocked failures.
- [x] Verified independent facial-expression evaluation.
- [x] Verified camera frame association with sessions.
- [x] Verified report generation and result storage.

**Test Results:**

- Tests Executed: 22
- Tests Passed: 22
- Tests Failed: 0

These automated tests validate software behavior using controlled test conditions and mocks where applicable.

### Local Integration Testing

A complete local test for one predefined scenario was performed using the actual FastAPI backend and real AI models.

**Verified Workflow:**

1. Started a new session.
2. Activated Scenario 1.
3. Uploaded a predefined facial test image.
4. Analyzed the image using ResMaskingNet before audio submission.
5. Generated a report containing the facial observation without a verbal response.
6. Uploaded a recorded audio test file.
7. Transcribed the audio using Whisper Small.
8. Classified the verbal emotion using Qwen2.5-VL-3B.
9. Evaluated the verbal answer against the reference label.
10. Verified that verbal and facial results appeared independently in the report.
11. Completed Scenario 1.
12. Ended the session early after completing one of four scenarios.
13. Viewed the final HTML report.

**Result:** Local integration test passed.

**Session Status:** `ended_early`
**Completed Scenarios:** 1 of 4
**Skipped Scenarios:** 0

The image and audio came from separate test sources. This test validates technical processing and reporting, not the interpretation of a single participant's synchronized behavior.

## 6. Remaining Tasks

### Physical NAO Integration

- [ ] Validate the complete automated workflow using the physical NAO V6.
- [ ] Verify audio and facial-image acquisition within the same physical interaction.
- [ ] Validate data transfer and AI processing during live robot operation.
- [ ] Test the complete four-scenario interaction workflow.
- [ ] Verify stable communication between NAO and the PC during full sessions.
- [ ] Test recovery behavior under physical robot and network failures.

### Evaluation and Reliability

- [ ] Measure end-to-end processing latency.
- [ ] Evaluate system reliability across repeated sessions.
- [ ] Validate camera capture quality under different lighting conditions.
- [ ] Test the system using additional predefined labeled scenarios.
- [ ] Review privacy safeguards and data-retention procedures.
- [ ] Resolve any integration issues identified during physical robot testing.

## 7. Current Project Status

**Status: Local AI and backend integration validated; full physical NAO workflow testing pending.**

The physical NAO V6 has been successfully used for microphone recording, camera acquisition, and SSH/SCP data transfer during earlier development.

Whisper Small, Qwen2.5-VL-3B, and ResMaskingNet have been integrated and tested locally with FastAPI.

A complete local test involving one predefined scenario was successfully performed, including verbal-response evaluation, independent facial-expression analysis, scenario completion, session termination, and report generation.

All 22 automated unit tests passed on November 16, 2026.

The next major milestone is validating the complete workflow on the physical NAO robot across all four scenarios.

The project remains in the technical prototype development and evaluation stage.

## 8. Data Directories

The project uses dedicated directories for acquired and processed data, including:

```text
data/
├── laptop_audio/
├── nao_audio/
├── nao_frames/
├── session_audio/
└── session_frames/
```

These directories support local storage of recorded audio and camera images. Captured test data should remain excluded from version control.

## 9. Project Scope

The project is designed to support structured emotion-recognition activities involving four target emotions:

- Happiness
- Sadness
- Anger
- Neutrality

The system uses predefined emotional images, open-ended verbal responses, and independent facial-expression analysis.

The verbal-processing branch evaluates the emotion described in the spoken response against the displayed image's reference label.

The facial-processing branch identifies visible facial expressions and records the results in the session report for specialist review.

The two branches are not compared against each other.

The current evaluation scope is limited to technical prototype testing using predefined labeled scenarios.

Testing with children with Autism Spectrum Disorder (ASD) is not part of the current implementation phase.

---

**Contributor:** Reem Abdulhameed
**Project:** NAO-Based Emotion Recognition System
**University:** University of Jeddah
**Academic Year:** 2026–2027
