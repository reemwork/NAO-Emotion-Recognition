"""Verbal answer evaluation endpoint.

The MLLM classifies transcribed speech (text only); this module compares the
predicted label with the scenario's reference label and persists Correct /
Incorrect / Unclear. Facial expressions remain independent observations.
"""
import backend
import requests
from fastapi import APIRouter, HTTPException
from backend.schemas import ChildResponse

router = APIRouter(tags=["Verbal Emotion Evaluation"])

def _backend():
    """Look up shared session state and the configured Qwen adapter."""
    # Use the already loaded package module (no recursive re-import).
    # This also preserves monkeypatched backend.app aliases in offline tests.
    return backend.app

@router.post("/api/response/submit")
def submit_response(data: ChildResponse):
    """Classify spoken text with Qwen and compare it with the scenario's known label.
    
        Correctness depends ONLY on the verbal description; camera predictions
        are recorded separately and do not affect this evaluation."""

    ctx = _backend()
    sessions = ctx.sessions
    scenarios_db = ctx.scenarios_db
    classify_emotion = ctx.classify_emotion
    record_scenario_issue = ctx.record_scenario_issue
    save_sessions = ctx.save_sessions

    session = sessions.get(data.session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    if session.get("status") != "active":
        raise HTTPException(
            status_code=409,
            detail="Session has already ended."
        )

    scenario = next(
        (
            item for item in scenarios_db
            if item["scenario_id"] == data.scenario_id
        ),
        None
    )

    if scenario is None:
        raise HTTPException(
            status_code=404,
            detail="Scenario not found."
        )

    spoken_text = data.spoken_text.strip()

    if not spoken_text:
        raise HTTPException(
            status_code=400,
            detail="Response cannot be empty."
        )

    if any(
        result["scenario_id"] == data.scenario_id
        for result in session["results"]
    ):
        raise HTTPException(
            status_code=409,
            detail="Response already submitted for this scenario."
        )

    # Step 1: Qwen sees the spoken text, NOT the scenario image/reference label.
    # This prevents the model from reading the answer directly.
    try:
        predicted_emotion = classify_emotion(spoken_text)

    except (requests.RequestException, RuntimeError) as error:
        record_scenario_issue(session, data.scenario_id, "processing_failed")
        print("MLLM classification failed:", error)
        raise HTTPException(
            status_code=503,
            detail="Emotion classification is unavailable."
        )

    # Step 2: Evaluate verbal correctness using the predefined reference label.
    # An 'Unclear' description is neither a correct nor an incorrect answer.
    reference_label = scenario["reference_label"]

    if predicted_emotion == "Unclear":
        evaluation = "Unclear"

    elif predicted_emotion == reference_label:
        evaluation = "Correct"

    else:
        evaluation = "Incorrect"

    # Step 3: Save the result in the current session
    result = {
        "scenario_id": data.scenario_id,
        "reference_label": reference_label,
        "spoken_text": spoken_text,
        "predicted_emotion": predicted_emotion,
        "evaluation": evaluation
    }

    # Link any images captured earlier; camera-first and audio-first both work.
    frames = session.get("captured_frames", {}).get(
        str(data.scenario_id), []
    )
    if frames:
        result["face_image_file"] = frames[-1]
        result["face_image_files"] = frames.copy()

    session["results"].append(result)
    save_sessions()

    return {
        "status": "success",
        "session_id": data.session_id,
        "saved_result": result,
        "total_responses": len(session["results"])
    }
