
"""Verbal answer evaluation endpoint.

The MLLM classifies transcribed speech (text only); this module compares
the predicted label with the scenario's reference label and persists
Correct / Incorrect / Unclear.

Facial expressions remain independent observations.
"""

import requests
from fastapi import APIRouter, HTTPException

import backend
from backend.schemas import ChildResponse


router = APIRouter(tags=["Verbal Emotion Evaluation"])


def _backend():
    """Look up shared session state and the configured Qwen adapter.

    Use the already loaded package module rather than recursively
    importing it. This also preserves monkeypatched backend.app
    aliases in offline tests.
    """
    return backend.app


@router.post("/api/response/submit")
def submit_response(data: ChildResponse):
    """Evaluate a verbal response against the scenario's reference label.

    Correctness depends only on the verbal classification.
    Facial observations do not affect this evaluation.
    """

    ctx = _backend()

    sessions = ctx.sessions
    scenarios_db = ctx.scenarios_db
    classify_emotion = ctx.classify_emotion
    record_scenario_issue = ctx.record_scenario_issue
    save_sessions = ctx.save_sessions

    # Step 1: Validate the session.
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

    # Ensure that the submitted response belongs to
    # the currently active scenario.
    if session.get("active_scenario_id") != data.scenario_id:
        raise HTTPException(
            status_code=409,
            detail="Response does not match the active scenario."
        )

    # Step 2: Validate the scenario.
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

    # Step 3: Validate the spoken response.
    spoken_text = data.spoken_text.strip()

    if not spoken_text:
        raise HTTPException(
            status_code=400,
            detail="Response cannot be empty."
        )

    # Prevent duplicate verbal results for one scenario.
    if any(
        result["scenario_id"] == data.scenario_id
        for result in session["results"]
    ):
        raise HTTPException(
            status_code=409,
            detail="Response already submitted for this scenario."
        )

    # Step 4: Classify the verbal response using local Qwen.
    # Qwen receives only spoken text, not the displayed
    # image or its predefined reference label.
    try:
        predicted_emotion = classify_emotion(spoken_text)

    except (requests.RequestException, RuntimeError) as error:
        record_scenario_issue(
            session,
            data.scenario_id,
            "processing_failed"
        )

        print("MLLM classification failed:", error)

        raise HTTPException(
            status_code=503,
            detail="Emotion classification is unavailable."
        ) from error

    # Step 5: Evaluate against the predefined image label.
    reference_label = scenario["reference_label"]

    if predicted_emotion == "Unclear":
        evaluation = "Unclear"

    elif predicted_emotion == reference_label:
        evaluation = "Correct"

    else:
        evaluation = "Incorrect"

    # Step 6: Save the verbal evaluation.
    result = {
        "scenario_id": data.scenario_id,
        "reference_label": reference_label,
        "spoken_text": spoken_text,
        "predicted_emotion": predicted_emotion,
        "evaluation": evaluation
    }

    # Link any frames captured for this scenario.
    # These references are for reporting only.
    # Facial classifications do not affect correctness.
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
