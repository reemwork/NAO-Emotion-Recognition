"""NAO Emotion Training FastAPI entry point.

Start with `python -m uvicorn backend.app:app --reload` from repository root.
Feature routers share the same sessions; verbal correctness uses text and
known scenario labels, not the independent facial classification.
"""
from fastapi import FastAPI
from backend import audio, vision, sessions_api, responses, reports, state
from backend.emotion_classifier import classify_emotion
from backend.schemas import ChildResponse, ScenarioEvent, SessionEnd, ScenarioRecovery, FacialResult

app = FastAPI(title="NAO Emotion Training Backend", version="1.0")

# One shared local session store, available to each feature's API handlers.
ROOT = state.ROOT
SCENARIOS_FILE = state.SCENARIOS_FILE
SESSIONS_FILE = state.SESSIONS_FILE
scenarios_db = state.scenarios_db
sessions = state.sessions
load_sessions = state.load_sessions
save_sessions = state.save_sessions

@app.get("/")
def read_root():
    """Health-check endpoint: confirms that the server is running."""
    return {"status": "online"}

# Register existing URL paths without changing the HTTP API contract.
for feature in (sessions_api, responses, reports, audio, vision):
    app.include_router(feature.router)

# Keep earlier callable names for scripts and existing offline tests.
record_scenario_issue = sessions_api.record_scenario_issue
start_session = sessions_api.start_session
end_session = sessions_api.end_session
get_next_scenario = sessions_api.get_next_scenario
start_scenario = sessions_api.start_scenario
complete_scenario = sessions_api.complete_scenario
recover_scenario = sessions_api.recover_scenario
get_session_results = sessions_api.get_session_results
submit_response = responses.submit_response
generate_session_report = reports.generate_session_report
view_session_report = reports.view_session_report
whisper_model = audio.whisper_model
transcribe_audio = audio.transcribe_audio
classify_facial_frame = vision.classify_facial_frame
upload_nao_audio = audio.upload_nao_audio
capture_nao_audio = audio.capture_nao_audio
evaluate_audio = audio.evaluate_audio
upload_camera_frame = vision.upload_camera_frame
upload_raw_camera_frame = vision.upload_raw_camera_frame
upload_session_frame = vision.upload_session_frame
evaluate_facial_frame = vision.evaluate_facial_frame
save_facial_result = vision.save_facial_result
