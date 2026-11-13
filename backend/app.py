import json
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from uuid import uuid4

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from backend.emotion_classifier import classify_emotion
from backend.schemas import (
    ChildResponse, ScenarioEvent, SessionEnd, ScenarioRecovery, FacialResult
)
from backend import audio, vision

app = FastAPI(
    title="NAO Emotion Training Backend",
    version="1.0"
)



ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_FILE = ROOT / "data" / "scenarios.json"

with open(SCENARIOS_FILE, "r", encoding="utf-8") as file:
    scenarios_db = json.load(file)
SESSIONS_FILE = ROOT / "data" / "sessions.json"


def load_sessions():
    if not SESSIONS_FILE.exists():
        return {}

    with open(SESSIONS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


sessions = load_sessions()


def save_sessions():
    SESSIONS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_file = SESSIONS_FILE.with_suffix(".json.tmp")

    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(
            sessions,
            file,
            indent=4,
            ensure_ascii=False
        )

    temp_file.replace(SESSIONS_FILE)

@app.get("/")
def read_root():
    return {
        "status": "online"
    }



def record_scenario_issue(session, scenario_id, reason):
    """Log a recoverable pipeline issue without treating it as an answer."""
    state = session.get("scenario_progress", {}).get(str(scenario_id))
    if state is not None and state.get("status") == "in_progress":
        state.setdefault("issues", []).append({
            "reason": reason,
            "recorded_at": datetime.now(timezone.utc).isoformat()
        })
        save_sessions()


@app.post("/api/session/start")
def start_session():
    session_id = str(uuid4())

    sessions[session_id] = {
        "session_id": session_id,
        "status": "active",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "active_scenario_id": None,
        "scenario_progress": {},
        "results": []
    }
    save_sessions()
    return {
        "status": "success",
        "session_id": session_id,
        "total_scenarios": len(scenarios_db)
    }


@app.post("/api/session/end")
def end_session(data: SessionEnd):
    session = sessions.get(data.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    # Repeated requests are safe and keep the original completion time.
    if session.get("status") != "active":
        return {
            "status": "success",
            "session_id": data.session_id,
            "session_status": session["status"],
            "ended_at": session.get("ended_at"),
            "completed_scenarios": sum(
                state.get("status") == "completed"
                for state in session.get("scenario_progress", {}).values()
            ),
            "skipped_scenarios": sum(
                state.get("status") == "skipped"
                for state in session.get("scenario_progress", {}).values()
            ),
            "total_scenarios": len(scenarios_db),
            "already_ended": True
        }

    if session.get("active_scenario_id") is not None:
        raise HTTPException(
            status_code=409,
            detail="Complete the active scenario before ending the session."
        )

    progress = session.get("scenario_progress", {})
    completed_count = sum(
        progress.get(str(scenario["scenario_id"]), {}).get("status")
        == "completed"
        for scenario in scenarios_db
    )
    skipped_count = sum(
        progress.get(str(scenario["scenario_id"]), {}).get("status")
        == "skipped"
        for scenario in scenarios_db
    )
    all_resolved = completed_count + skipped_count == len(scenarios_db)

    if not all_resolved:
        session["status"] = "ended_early"
    elif skipped_count:
        session["status"] = "completed_with_skips"
    else:
        session["status"] = "completed"
    session["ended_at"] = datetime.now(timezone.utc).isoformat()
    save_sessions()

    return {
        "status": "success",
        "session_id": data.session_id,
        "session_status": session["status"],
        "ended_at": session["ended_at"],
        "completed_scenarios": completed_count,
        "skipped_scenarios": skipped_count,
        "total_scenarios": len(scenarios_db),
        "already_ended": False
    }


@app.get("/api/scenario/next")
def get_next_scenario(index: int = 0):
    if index < len(scenarios_db):
        return {
            "status": "success",
            "has_more": True,
            "scenario": scenarios_db[index]
        }

    return {
        "status": "success",
        "has_more": False,
        "message": "All scenarios completed."
    }




@app.post("/api/scenario/start")
def start_scenario(data: ScenarioEvent):
    session = sessions.get(data.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    if session.get("status") != "active":
        raise HTTPException(status_code=409, detail="Session is not active.")

    if not any(
        scenario["scenario_id"] == data.scenario_id
        for scenario in scenarios_db
    ):
        raise HTTPException(status_code=404, detail="Scenario not found.")

    active_id = session.get("active_scenario_id")
    if active_id is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Scenario {active_id} is already in progress."
        )

    progress = session.setdefault("scenario_progress", {})
    key = str(data.scenario_id)
    if key in progress or any(
        result["scenario_id"] == data.scenario_id
        for result in session["results"]
    ):
        raise HTTPException(
            status_code=409,
            detail="This scenario was already started or evaluated."
        )

    started_at = datetime.now(timezone.utc).isoformat()
    progress[key] = {
        "status": "in_progress",
        "started_at": started_at,
        "completed_at": None
    }
    session["active_scenario_id"] = data.scenario_id
    save_sessions()

    return {
        "status": "success",
        "session_id": data.session_id,
        "scenario_id": data.scenario_id,
        "scenario_status": "in_progress",
        "started_at": started_at
    }


@app.post("/api/scenario/complete")
def complete_scenario(data: ScenarioEvent):
    session = sessions.get(data.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    if not any(
        scenario["scenario_id"] == data.scenario_id
        for scenario in scenarios_db
    ):
        raise HTTPException(status_code=404, detail="Scenario not found.")

    progress = session.get("scenario_progress", {})
    state = progress.get(str(data.scenario_id))
    if (
        state is None
        or state.get("status") != "in_progress"
        or session.get("active_scenario_id") != data.scenario_id
    ):
        raise HTTPException(
            status_code=409,
            detail="This scenario is not currently in progress."
        )

    # Completion requires a saved response; use scenario/recovery to skip
    # a scenario when there is no usable verbal response.
    if not any(
        result["scenario_id"] == data.scenario_id
        for result in session["results"]
    ):
        raise HTTPException(
            status_code=409,
            detail="Cannot complete a scenario without a saved verbal response."
        )

    completed_at = datetime.now(timezone.utc).isoformat()
    state["status"] = "completed"
    state["completed_at"] = completed_at
    session["active_scenario_id"] = None
    save_sessions()

    return {
        "status": "success",
        "session_id": data.session_id,
        "scenario_id": data.scenario_id,
        "scenario_status": "completed",
        "started_at": state["started_at"],
        "completed_at": completed_at
    }


@app.post("/api/scenario/recovery")
def recover_scenario(data: ScenarioRecovery):
    session = sessions.get(data.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.get("status") != "active":
        raise HTTPException(status_code=409, detail="Session is not active.")

    state = session.get("scenario_progress", {}).get(str(data.scenario_id))
    if (
        state is None
        or state.get("status") != "in_progress"
        or session.get("active_scenario_id") != data.scenario_id
    ):
        raise HTTPException(
            status_code=409,
            detail="This scenario is not currently in progress."
        )

    if any(
        result["scenario_id"] == data.scenario_id
        for result in session["results"]
    ):
        raise HTTPException(
            status_code=409,
            detail="The scenario already has a saved verbal response."
        )

    event = {
        "action": data.action,
        "reason": data.reason,
        "recorded_at": datetime.now(timezone.utc).isoformat()
    }
    state.setdefault("recovery_events", []).append(event)

    if data.action == "skip":
        state["status"] = "skipped"
        state["skip_reason"] = data.reason
        state["completed_at"] = event["recorded_at"]
        session["active_scenario_id"] = None

    save_sessions()
    return {
        "status": "success",
        "session_id": data.session_id,
        "scenario_id": data.scenario_id,
        "scenario_status": state["status"],
        "action": data.action,
        "reason": data.reason
    }


@app.post("/api/response/submit")
def submit_response(data: ChildResponse):

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

    # Step 1: Classify the verbal response using Qwen
    try:
        predicted_emotion = classify_emotion(spoken_text)

    except (requests.RequestException, RuntimeError) as error:
        record_scenario_issue(session, data.scenario_id, "processing_failed")
        print("MLLM classification failed:", error)
        raise HTTPException(
            status_code=503,
            detail="Emotion classification is unavailable."
        )

    # Step 2: Compare prediction with the reference label
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

    # Attach images captured before the verbal answer was submitted.
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

#Nada's
@app.get("/api/session/{session_id}")
def get_session_results(session_id: str):

    session = sessions.get(session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    results = session["results"]

    summary = {
        "correct": sum(
            r["evaluation"] == "Correct"
            for r in results
        ),
        "incorrect": sum(
            r["evaluation"] == "Incorrect"
            for r in results
        ),
        "unclear": sum(
            r["evaluation"] == "Unclear"
            for r in results
        )
    }

    return {
        "status": "success",
        "session_id": session_id,
        "total_scenarios": len(scenarios_db),
        "total_responses": len(results),
        "session_status": session.get("status", "active"),
        "session_started_at": session.get("started_at"),
        "session_ended_at": session.get("ended_at"),
        "active_scenario_id": session.get("active_scenario_id"),
        "scenario_progress": session.get("scenario_progress", {}),
        "skipped_scenarios": sum(
            state.get("status") == "skipped"
            for state in session.get("scenario_progress", {}).values()
        ),
        "captured_frames": session.get("captured_frames", {}),
        "results": results,
        "summary": summary
    }


@app.get("/api/session/{session_id}/report")
def generate_session_report(session_id: str):

    session = sessions.get(session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    results = session["results"]

    correct = sum(
        r.get("evaluation") == "Correct"
        for r in results
    )

    incorrect = sum(
        r.get("evaluation") == "Incorrect"
        for r in results
    )

    unclear = sum(
        r.get("evaluation") == "Unclear"
        for r in results
    )

    evaluated = correct + incorrect

    accuracy = (
        round(correct / evaluated * 100, 2)
        if evaluated > 0 else None
    )

    facial_emotions = []
    mock_count = 0
    scenario_reports = []

    for result in results:

        observations = result.get(
            "facial_observations", []
        )

        real_observations = []

        for obs in observations:
            if obs.get("source") == "mock":
                mock_count += 1

            elif obs.get("source") == "resmaskingnet":
                real_observations.append(obs)
                facial_emotions.append(
                    obs["dominant_emotion"]
                )

        verbal_emotion = result.get(
            "predicted_emotion"
        )

        if real_observations:

            dominant_facial = Counter(
                obs["dominant_emotion"]
                for obs in real_observations
            ).most_common(1)[0][0]

            if verbal_emotion == "Unclear":
                comparison = "Unavailable"

            elif verbal_emotion == dominant_facial:
                comparison = "Agreement"

            else:
                comparison = "Mismatch"

        else:
            dominant_facial = None
            comparison = "Unavailable"

        scenario_reports.append({
            "scenario_id": result["scenario_id"],
            "reference_label": result["reference_label"],
            "spoken_text": result["spoken_text"],
            "verbal_emotion": verbal_emotion,
            "answer_evaluation": result["evaluation"],
            "dominant_facial_expression": dominant_facial,
            "verbal_facial_comparison": comparison
        })

    most_frequent_facial = (
        Counter(facial_emotions).most_common(1)[0][0]
        if facial_emotions else None
    )

    return {
        "session_id": session_id,
        "report_type": "Technical Prototype Report",
        "total_scenarios": len(scenarios_db),
        "completed_scenarios": len(results),
        "verbal_performance": {
            "correct": correct,
            "incorrect": incorrect,
            "unclear": unclear,
            "accuracy_excluding_unclear": accuracy
        },
        "facial_analysis": {
            "model_observations": len(facial_emotions),
            "mock_observations_excluded": mock_count,
            "most_frequent_expression": most_frequent_facial
        },
        "scenario_details": scenario_reports
    }

@app.get(
    "/api/session/{session_id}/report/view",
    response_class=HTMLResponse
)
def view_session_report(session_id: str):

    report = generate_session_report(session_id)

    performance = report["verbal_performance"]
    facial = report["facial_analysis"]

    accuracy = performance["accuracy_excluding_unclear"]
    accuracy_text = (
        f"{accuracy}%"
        if accuracy is not None
        else "N/A"
    )

    rows = ""

    for item in report["scenario_details"]:
        rows += f"""
        <tr>
            <td>{item['scenario_id']}</td>
            <td>{escape(str(item['reference_label']))}</td>
            <td>{escape(str(item['spoken_text']))}</td>
            <td>{escape(str(item['verbal_emotion']))}</td>
            <td>{escape(str(item['answer_evaluation']))}</td>
            <td>{escape(str(item['dominant_facial_expression'] or 'N/A'))}</td>
            <td>{escape(str(item['verbal_facial_comparison']))}</td>
        </tr>
        """

    if not rows:
        rows = '<tr><td colspan="7">No completed scenarios.</td></tr>'

    styles = """
    <style>
        body {
            font-family: Arial, sans-serif;
            color: #203047;
            margin: 40px;
            line-height: 1.6;
        }
        h1, h2 { color: #174a75; }
        .subtitle { color: #66788a; }
        .section {
            background: #f1f6fa;
            padding: 18px;
            border-radius: 8px;
            margin: 20px 0;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }
        th, td {
            border: 1px solid #cad6df;
            padding: 8px;
            text-align: left;
            overflow-wrap: anywhere;
        }
        th { background: #e5eef5; }
        .note { font-size: 12px; color: #66788a; }
        @media print {
            body { margin: 15mm; }
            .section { break-inside: avoid; }
        }
    </style>
    """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>NAO Session Report</title>
        {styles}
    </head>
    <body>
        <h1>NAO Emotion Recognition</h1>
        <p class="subtitle">Technical Prototype Session Report</p>

        <p><strong>Session ID:</strong> {escape(session_id)}</p>
        <p><strong>Completed Scenarios:</strong>
        {report['completed_scenarios']} /
        {report['total_scenarios']}</p>

        <div class="section">
            <h2>Verbal Performance</h2>
            <p>Correct: {performance['correct']}</p>
            <p>Incorrect: {performance['incorrect']}</p>
            <p>Unclear: {performance['unclear']}</p>
            <p>Accuracy (excluding unclear):
            {accuracy_text}</p>
        </div>

        <div class="section">
            <h2>Facial Expression Analysis</h2>
            <p>Model Observations:
            {facial['model_observations']}</p>
            <p>Mock Observations Excluded:
            {facial['mock_observations_excluded']}</p>
            <p>Most Frequent Expression:
            {escape(str(facial['most_frequent_expression'] or 'N/A'))}</p>
        </div>

        <h2>Scenario Details</h2>
        <table>
            <tr>
                <th>ID</th>
                <th>Reference</th>
                <th>Spoken Response</th>
                <th>Verbal Emotion</th>
                <th>Evaluation</th>
                <th>Facial Expression</th>
                <th>Comparison</th>
            </tr>
            {rows}
        </table>

        <p class="note">
            Prototype report generated from predefined test scenarios.
            Mock facial observations are excluded from model results.
            This report is not a clinical assessment.
        </p>
    </body>
    </html>
    """

# Register the extracted feature endpoints under their original URLs.
app.include_router(audio.router)
app.include_router(vision.router)

# Keep public callable names for existing scripts and offline tests.
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
