# NAO-Based Emotion Recognition System

**Graduation Project | University of Jeddah | 2026–2027**

An AI-powered humanoid robot system designed to support structured emotion-recognition activities for children with Autism Spectrum Disorder (ASD).

The project combines **Human-Robot Interaction (HRI), Natural Language Processing (NLP), Computer Vision (CV), and Multimodal Large Language Models (MLLMs)** to evaluate verbal emotion identification and analyze observed facial expressions.

**Status:** In Development — Local AI and backend integration validated; physical NAO end-to-end testing pending.

## 1. Project Overview

The system uses the NAO V6 humanoid robot to conduct interactive emotion-recognition sessions involving four target emotions:

- Happiness
- Sadness
- Anger
- Neutrality

During each interaction, a predefined emotional image is displayed on an external screen while NAO asks an open-ended question about the image.

The participant's spoken response is recorded and transcribed into text. A locally hosted language model identifies the emotion described in the response, which is compared against the displayed image's predefined reference label to evaluate answer correctness.

Separately, NAO captures facial images for facial-expression analysis. A computer vision model classifies visible facial expressions and records confidence scores.

**The verbal and facial processing branches are independent.** Facial observations are reported separately and are not compared with verbal classifications or used to determine answer correctness.

The current project focuses on prototype development and technical evaluation using predefined labeled scenarios.

**Testing with children with ASD is not included in the current scope.**

## 2. System Architecture

The system consists of two independent processing branches, coordinated through an external computer.

### Branch A: Verbal Emotion Evaluation

1. Display a predefined emotional image.
2. NAO asks an open-ended question about the image.
3. Record the spoken response using NAO's microphone.
4. Transfer the recorded audio to the external computer.
5. Convert speech into text using Whisper Small.
6. Use Qwen2.5-VL-3B to classify the emotion described in the transcribed response.
7. Compare the predicted emotion **only** with the displayed image's predefined reference label.
8. Record the outcome as Correct, Incorrect, or Unclear.

The supported verbal emotion labels are:

- Happy
- Sad
- Angry
- Neutral

The classifier may return Unclear when the response cannot be reliably classified.

The language model receives the transcribed response for classification, not the displayed emotional image.

### Branch B: Facial Expression Analysis

1. Capture facial images using NAO's camera.
2. Transfer captured images to the external computer.
3. Analyze facial expressions using ResMaskingNet.
4. Record the detected facial expression and confidence score.
5. Store the observations independently in the session report.

Facial-expression analysis does not require a verbal response to be submitted first.

Facial-expression predictions are descriptive observations of visible expressions, not verified internal emotional states.

They are not used to determine verbal-answer correctness.

### System Workflow

```text
NAO V6 Robot
    |
    +-- Displayed Emotional Scenario
    |       |
    |       +-- Spoken Response
    |               |
    |               v
    |          Whisper Small
    |               |
    |               v
    |          Qwen2.5-VL-3B
    |               |
    |               v
    |          Reference Label Comparison
    |               |
    |               v
    |          Correct / Incorrect / Unclear
    |
    +-- Camera Capture
            |
            v
       ResMaskingNet
            |
            v
       Facial Expression + Confidence
            |
            v
       Independent Facial Observations

                    |
                    v
            Session Report
             /          \
     Verbal Results    Facial Observations
```

All AI inference runs on the external computer rather than directly on NAO.

### Final Output

The system generates structured session reports containing:

- Verbal emotion classification and answer correctness.
- Transcribed spoken responses.
- Predicted facial expressions and confidence scores.
- Captured facial-image references.
- Verbal performance statistics.
- Independent facial-expression observations.
- Session and scenario information.

The report presents verbal and facial results in separate sections.

**No verbal–facial comparison, agreement score, mismatch score, or engagement measurement is performed.**

## 3. Preliminary AI Model Evaluation

### Language Model Evaluation

Three candidate models were investigated:

- Qwen2.5-VL-3B
- Gemma 3 4B
- Qwen3-VL-4B

The preliminary experiments examined classification accuracy, processing time, and input configurations.

| Model | Input | Accuracy | Average Time |
|---|---|---|---|
| Qwen2.5-VL-3B | Text Only | 90% | 3.87 s |
| Gemma 3 4B | Text Only | 85% | 2.75 s |
| Qwen2.5-VL-3B | Image + Text | 60% | 6.14 s |
| Gemma 3 4B | Image + Text | 70% | 5.19 s |
| Qwen3-VL-4B | Image + Text | N/A | N/A |

Each completed configuration was evaluated using 20 synthetic test cases.

Qwen3-VL-4B did not complete classification within the configured reasoning token limit.

**Selected Model: Qwen2.5-VL-3B**, using text-only input and deployed locally through Ollama.

These results are preliminary and do not establish general performance on real-world participant responses.

### Facial Expression Model Evaluation

Three pretrained facial-expression recognition models were compared using 70 labeled images.

| Model | Accuracy |
|---|---|
| ResNet-18 | 71.43% |
| DeepFace | 62.86% |
| ResMaskingNet | 72.86% |

ResMaskingNet achieved the highest overall accuracy in this preliminary experiment and was selected for facial-expression analysis.

The preliminary facial-model evaluation covered seven facial-expression categories, while the displayed emotion-recognition scenarios focus on four target emotions.

## 4. Implementation Progress

### Implemented and Tested

- Physical NAO microphone recording and camera acquisition.
- SSH/SCP transfer of audio and image files between NAO and the development computer.
- FastAPI backend for session and scenario management.
- Local Whisper Small speech-to-text transcription.
- Local Qwen2.5-VL-3B verbal emotion classification through Ollama.
- Verbal-response evaluation against predefined scenario reference labels.
- Local ResMaskingNet facial-expression classification.
- Independent storage of verbal results and facial observations.
- Automated JSON and HTML session reporting.
- Local integration testing using real AI models and predefined test files.
- Successful execution of 22 automated unit tests.

### Local Integration Validation

A local integration test was conducted using the FastAPI backend and real model inference.

The test included:

1. Creating a session.
2. Activating a predefined scenario.
3. Uploading a facial test image.
4. Performing facial-expression analysis before verbal-response submission.
5. Uploading a recorded audio test file.
6. Transcribing the audio using Whisper Small.
7. Classifying the verbal emotion using Qwen2.5-VL-3B.
8. Comparing the verbal prediction with the scenario reference label.
9. Generating JSON and HTML reports with independent verbal and facial sections.
10. Completing the scenario and ending the session.

**Local Integration Result: Passed**

The test used separately supplied image and audio files.

It does not establish successful synchronized capture or complete end-to-end operation on the physical NAO robot.

### Remaining Work

- Full end-to-end testing using the physical NAO V6 robot.
- Validation of the complete four-scenario interaction workflow.
- Verification of live audio and camera acquisition within the same interaction.
- Testing robot-to-PC communication reliability.
- Measuring system processing latency.
- Testing error handling and recovery.
- Reviewing privacy safeguards and data-retention procedures.
- Further robustness and usability testing.

## 5. Technologies

**Programming:** Python

**Robot Platform:** NAO V6, NAOqi SDK, Choregraphe

**Backend:** FastAPI

**Machine Learning & AI:** Whisper Small, Qwen2.5-VL-3B, Ollama, ResMaskingNet, DeepFace (preliminary evaluation)

**Image Processing:** OpenCV, Pillow

**Communication & Development:** SSH, SCP, HTTP, Git, GitHub

**Testing:** Python unittest

Whisper Small, Qwen2.5-VL-3B, and ResMaskingNet have been integrated and tested locally.

DeepFace was investigated during preliminary facial-expression model evaluation and is not the selected active facial-classification model.

Full physical NAO integration validation remains pending.

## 6. Privacy and Data Handling

The system is designed to process captured audio and facial images on the local development computer.

Recorded audio and captured images are intended to remain within the authorized development environment.

Local audio and image directories are excluded from Git tracking to reduce the risk of committing captured data to the repository.

The system currently uses predefined technical test scenarios and does not involve children with ASD.

Before any future participant testing, additional safeguards will be required, including:

- Appropriate ethical approval and participant consent.
- Secure access to recorded data.
- Clear data-retention and deletion procedures.
- Authentication and authorization.
- Privacy and participant-protection controls.

## 7. Evaluation Plan

The integrated prototype will be evaluated using predefined labeled technical scenarios.

### Verbal Emotion Evaluation

- Verify speech transcription using recorded test audio.
- Evaluate the predicted verbal emotion against the displayed image's predefined reference label.
- Record Correct, Incorrect, and Unclear outcomes.
- Measure verbal classification accuracy and the frequency of unclear responses.
- Examine classification failures and ambiguous responses.

### Facial Expression Analysis

- Verify successful facial-image acquisition and processing.
- Record predicted facial expressions and confidence scores.
- Evaluate facial-classification performance separately using labeled test images.
- Document cases where no face is detected or facial inference fails.

Facial evaluation is conducted independently of verbal-answer correctness.

### System Integration and Reliability

- Test the complete four-scenario workflow using the physical NAO V6.
- Measure processing latency and session completion.
- Evaluate robot-to-PC communication reliability.
- Test retry, skip, and recovery behavior.
- Verify that verbal and facial results are independently recorded in session reports.
- Review local storage and privacy safeguards.

The current evaluation is limited to technical prototype validation. No testing with children with ASD is included.

## 8. Documentation

- [Developer Guide](docs/CODE_WALKTHROUGH.md) — System architecture, code structure, module responsibilities, and API workflow.
- [NAO Integration Guide](docs/NAO_INTEGRATION.md) — Robot setup, startup instructions, and integration validation.
- [Development Progress](PROGRESS.md) — Data acquisition, backend development, completed work, and remaining tasks.

## 9. Project Status

**Current Status: Local AI and backend integration validated; physical NAO end-to-end validation pending.**

The physical NAO V6 has been used successfully for audio recording, camera acquisition, and robot-to-PC file transfer during earlier development.

The AI processing components and FastAPI backend have been integrated and tested locally with predefined audio and image test files.

Automated reporting and independent verbal/facial processing have also been verified locally.

The next major milestone is validating the complete interaction workflow on the physical NAO robot across all four predefined scenarios.

---

**University:** University of Jeddah
**Academic Year:** 2026–2027
**Project Type:** Computer Science Senior Project