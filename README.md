# NAO-Based Emotion Recognition System

**Graduation Project | University of Jeddah | 2026–2027**

An AI-powered humanoid robot system designed to support structured emotion-recognition activities for children with Autism Spectrum Disorder (ASD).

The project combines **Human-Robot Interaction (HRI), Natural Language Processing (NLP), Computer Vision (CV), and Multimodal Large Language Models (MLLMs)** to evaluate verbal emotion identification and analyze observed facial expressions.

**Status:** In Development — Graduation Project

## Developer documentation

For a file-by-file code walkthrough, endpoint flow, model boundaries and
contributor guidance, see [Developer Guide](docs/CODE_WALKTHROUGH.md).
Each Python module also has English function docstrings and targeted comments.

## 1. Project Overview

The system uses the NAO V6 humanoid robot to conduct interactive emotion-recognition sessions involving four target emotions:

- Happiness
- Sadness
- Anger
- Neutrality

During each interaction, an emotional image is displayed on an external screen while NAO asks an open-ended question about the image.

The participant's spoken response is recorded and transcribed into text. A language model then identifies the emotion described in the response, which is compared against the image's predefined emotion label to evaluate answer correctness.

Separately, NAO captures facial images for expression classification. The verbal and facial results are compared descriptively and documented for specialist review.

The current project focuses on prototype development and technical evaluation. **Testing with children with ASD is not included in the current scope.**

## 2. System Architecture

The proposed system consists of two independent processing branches.

### Branch A: Verbal Emotion Assessment

1. Display a predefined emotional image.
2. NAO asks an open-ended question.
3. Record the spoken response using NAO's microphone.
4. Convert speech into text using Whisper.
5. Use Qwen2.5-VL-3B to classify the emotion described in the transcribed text.
6. Compare the predicted emotion against the image's predefined reference label.
7. Record the result as Correct, Incorrect, or Unclear.

The language model receives only the transcribed response for classification, preventing direct access to the expected answer through the displayed image.

### Branch B: Facial Expression Analysis

1. Capture facial images using NAO's camera.
2. Detect and process facial regions.
3. Classify visible facial expressions using a computer vision model.
4. Record the dominant facial expression and confidence score.

Facial expressions are analyzed independently and are not used to determine verbal-answer correctness.

### Final Output

The proposed system combines results from both branches to produce:

- Verbal emotion classification and response correctness.
- Facial expression classification and confidence scores.
- Descriptive verbal–facial comparison.
- Structured session reports summarizing performance and observed expressions.

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

Each completed configuration was evaluated using 20 synthetic test cases. Qwen3-VL-4B did not complete classification within the configured reasoning token limit.

**Initial selection: Qwen2.5-VL-3B**, with text-only input, deployed locally through Ollama.

These results are preliminary and do not establish general performance on real-world participant responses.

### Facial Expression Model Evaluation

Three pretrained facial expression recognition models were compared using 70 labeled images:

| Model | Accuracy |
|---|---|
| ResNet-18 | 71.43% |
| DeepFace | 62.86% |
| ResMaskingNet | 72.86% |

ResMaskingNet achieved the highest overall accuracy in this preliminary experiment and was selected for the proposed facial analysis component.

The evaluation covered seven facial-expression categories, while the image-based emotion-recognition activity focuses on four target emotions.

## 4. Implementation Progress

### Implemented and Tested

- NAO camera acquisition using NAOqi APIs.
- Audio recording from the physical NAO robot.
- Image and audio transfer between NAO and the development computer.
- SSH/SCP-based file transfer workflows.
- FastAPI endpoints for session initialization, scenario retrieval, response submission, and camera-frame handling.
- Virtual NAO camera-frame transfer to the backend.
- Preliminary standalone testing of speech transcription and facial expression analysis.

### In Progress / Planned

- Integrating the selected local MLLM into the complete interaction pipeline.
- Integrating the selected facial-expression recognition model.
- Synchronizing verbal and facial processing during full sessions.
- Implementing the final response evaluation and comparison workflow.
- Generating automated session reports.
- Conducting end-to-end prototype testing using predefined labeled scenarios.

## 5. Technologies

**Programming:** Python

**Robot Platform:** NAO V6, NAOqi SDK, Choregraphe

**Backend:** FastAPI

**Machine Learning & AI:** Whisper Small, Qwen2.5-VL-3B, Ollama, DeepFace, ResMaskingNet

**Image Processing:** OpenCV, Pillow

**Communication & Development:** SSH, SCP, Git, GitHub

Some models listed above were evaluated or selected during preliminary experiments and are not yet integrated into the final system.

## 6. Privacy and Data Handling

The system is designed to process captured audio and images on the local development computer.

Recorded audio and captured images are excluded from Git tracking to reduce the risk of uploading participant data to the repository.

The project is currently evaluated using predefined test scenarios and does not involve children with ASD.

## 7. Evaluation Plan

The integrated prototype will be evaluated using:

