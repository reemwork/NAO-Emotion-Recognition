# Single-command NAO session coordinator (experimental)

These are **new companion scripts**, not replacements for the team's existing modules. Copy `run_session.py` and `START_NAO.ps1` into the repository root, beside `backend/` and `data/`.

PowerShell from repository root:

```powershell
.\START_NAO.ps1 -NaoIP 169.254.247.199
```

Prerequisites:
- Python venv with `requests`, `uvicorn`, and existing backend dependencies.
- Ollama running locally, `ollama list` includes `qwen2.5vl:3b`.
- SSH key login: `ssh nao@ROBOT_IP "python -c 'import naoqi; print(1)'"`.
- Physical NAO permits remote Python execution with `naoqi`, NAOqi services `ALTextToSpeech`, `ALAudioRecorder`, `ALPhotoCapture`.
- Actual image files `data/scenario_images/{happy,sad,angry,neutral}_01.jpg` exist and a suitable external display is available.
- Existing app's transcript model `whisper small` loads, HTTP APIs are working.

The launcher opens FastAPI and `run_session.py` checks Ollama and robot availability, creates a backend session, loops through `data/scenarios.json`, opens each scenario image on PC, asks a question using robot TTS, records 8 seconds of robot audio and takes a robot image, transfers both through SCP, sends them to session-scoped APIs, then closes the session and writes a JSON report under `data/`.

It can replay prerecorded scenarios without a robot:

```powershell
python run_session.py --samples-dir .\test_captures
```

where `test_captures` contains `scenario_1.wav` and `scenario_1.jpg`, etc. This still uses *real* Whisper, Ollama and backend, and needs its services.

**Known current limitations (read before demo):**
- Physical robot capture code has **not been hardware-tested** and NAOqi `ALPhotoCapture.takePicture` return/output formats may vary.
- User must prearrange the external monitor/browser. Browser opens image but does not guarantee fullscreen or moving it onto the external screen.
- The existing facial `/api/facial/result` endpoint explicitly records `source: mock`. This coordinator **never calls it** or fabricates CV data. Full facial-classification integration is still needed from the team.
- The question is a single generic question; robot interaction team may replace this with scenario-specific Choregraphe behavior.
- Audio and frame acquisition are coordinated per scenario but not precisely synchronized/timestamp aligned.
- Errors result in a `skipped` scenario rather than a false `Incorrect` or `Unclear` score.
- Session API and unencrypted private material are restricted to local PC; additional authentication/privacy controls needed before real participant use.
- Do **not** run legacy `backend/watch.py` simultaneously with this coordinator.
