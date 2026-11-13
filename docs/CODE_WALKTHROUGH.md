# Developer Guide — NAO Emotion Recognition

This guide is written for teammates who need to read or modify the project
without knowing the original implementation. **Read the module docstrings
and function docstrings in the code too**: they explain inputs, decisions,
side effects and edge cases.

## Project behavior and scope

NAO presents an emotion scenario. The robot captures a WAV answer and
facial frames; a PC performs the AI processing. There are two **independent**
outputs:

1. **Verbal correctness:** Whisper transcribes the recording. A local Qwen
   classifier sees **text only** and returns Happy, Sad, Angry, Neutral or
   Unclear. The backend compares this prediction against the predefined
   scenario reference label to produce Correct, Incorrect or Unclear.
2. **Facial observation:** A camera frame is analyzed independently by the
   selected CV adapter. It returns a visible facial-expression label and
   confidence. It does **not** decide if the verbal answer is correct, and
   must not be used to infer a clinical diagnosis or true inner feeling.

The final report compares these outputs as Agreement, Mismatch or
Unavailable **for description only**. There are no actual ASD child trials
in the current technical-prototype evaluation.

## Source-code map

| File | Read it when you need to... |
| --- | --- |
| `backend/app.py` | Start FastAPI, understand router registration and compatibility aliases |
| `backend/state.py` | Find the central scenarios file, session dictionary and JSON persistence |
| `backend/sessions_api.py` | Trace new sessions, scenario start/complete, retry/skip and session ending |
| `backend/responses.py` | Understand the Qwen classification call and verbal Correct/Incorrect/Unclear decision |
| `backend/reports.py` | Understand JSON/HTML session reports, summary metrics and facial alignment |
| `backend/audio.py` | Handle standalone WAV uploads, robot WAV copying and session-aware speech evaluation |
| `backend/transcribe_audio.py` | Understand how legacy Whisper-small transcription is loaded and called |
| `backend/emotion_classifier.py` | See the actual local Qwen/Ollama request, model prompt and response validation |
| `backend/vision.py` | Receive/save JPEG or raw RGB camera frames and store facial observations |
| `backend/facial_classifier.py` | See the optional local RMN/ResMaskingNet adapter and confidence checks |
| `backend/schemas.py` | See request payload types and validation rules |
| `backend/nao_transfer.py` | Transfer captured NAO audio/images into one specified session/scenario |
| `backend/watch.py` | Understand the older non-session-aware camera/audio watcher |
| `tests/test_backend_workflow.py` | Learn the expected API behavior through offline unit tests |
| `experiments/mllm/` | Inspect earlier text-only and image+text model comparisons (not live endpoints) |
| `archive/` | Inspect legacy DeepFace and earlier robot-transfer experiments (not active pipeline) |

## Data files and robot behavior

- `data/scenarios.json` defines each `scenario_id`, displayed `image_path`
  and authoritative `reference_label` (four scenario emotion classes).
- `data/mllm_test_cases.json` defines benchmark `id`, `scenario_id`,
  sample `response` and expected verbal `expected` label.
- `data/sessions.json` is created locally during runs; it persists session
  progress, answers, audio/image file references and facial observations.
- `nao/data_capture/` contains the Choregraphe project and robot-side
  recording behavior. Review it before changing the robot's file paths.

**Why not comments inside JSON?** JSON does not support comments. This guide
documents each configuration field without breaking machine-readable files.

## Typical API workflow

1. `POST /api/session/start` creates a unique `session_id`.
2. `GET /api/scenario/next?index=0` selects a configured scenario.
3. `POST /api/scenario/start` activates the `scenario_id` in that session.
4. `POST /api/camera/session-frame` saves a frame with the same two IDs.
5. `POST /api/audio/evaluate` saves the WAV, runs English Whisper STT,
   classifies the transcript with Qwen, and persists the verbal result.
   Images and audio can arrive in either order.
6. `POST /api/facial/evaluate` classifies the latest captured frame and
   records an independent, real-model facial observation.
7. `POST /api/scenario/complete` finishes an answered scenario. Alternatively,
   `POST /api/scenario/recovery` retries/skips a scenario with no usable
   verbal response.
8. `POST /api/session/end` ends the session.
9. `GET /api/session/{session_id}/report` or
   `GET /api/session/{session_id}/report/view` returns the summary.

All existing URLs are preserved by the refactor. Swagger is available at
`http://127.0.0.1:8000/docs` after the server starts.

## Important behavior you must not confuse

- `Neutral` describes a neutral emotion; `Unclear` means insufficient
  evidence in the spoken description.
- Four classes are used for *displayed scenarios/verbal correctness*.
  The independent CV classifier can report seven facial-expression classes.
- The session-aware `/api/audio/evaluate` currently transcribes **English**.
  The separate **legacy** `transcribe_audio.py` helper is configured with
  `language="ar"` (Arabic), and `/api/audio/upload` uses that helper.
  The paths are documented distinctly; do not silently assume one language.
- `/api/facial/result` stores `source="mock"` observations for development
  only; they are excluded from the report's real-model statistics.
- `/api/facial/evaluate` currently calls the `rmn` package adapter. Before
  replacing it with a teammate's definitive ResMaskingNet code, **confirm
  her model weights and preprocessing match**. The restructuring does not
  replace the model or verify that match.
- The prototype uses local files and mutable in-memory session state backed
  by JSON; it is not yet a multi-worker production database.
- Legacy `watch.py` and archived transfer scripts do not attach session IDs.
  `nao_transfer.py` is the explicit, session-aware bridge.

## Starting and testing

From the repository root, with the project's Python environment active:

```powershell
python -m unittest tests.test_backend_workflow -v
python -m uvicorn backend.app:app --reload
```

Model/robot calls are mocked in the unit tests. Passing tests does not
prove a physical NAO connection, actual microphone quality, local Ollama
availability, or a teammate-specific CV model. Test those separately
with authorized, predefined test images and WAV files.

## Where should a teammate make a change?

- To adjust **spoken-emotion classification**: start in
  `backend/emotion_classifier.py` (Qwen prompt/output), then inspect
  `backend/responses.py` (reference-label comparison).
- To adjust **speech-to-text**: read `backend/audio.py` and
  `backend/transcribe_audio.py`; confirm the intended language.
- To change **frame ingestion**: edit `backend/vision.py`.
  To replace **CV inference**: edit `backend/facial_classifier.py` only
  after verifying the teammate's approved code and weights.
- To modify **session rules**: edit `backend/sessions_api.py` and tests.
- To change **reports**: edit `backend/reports.py` and tests.
- To add/change **request formats**: edit `backend/schemas.py`.
- Keep `backend/app.py` small: add router registrations, not business logic.
