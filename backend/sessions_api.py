"""Session and scenario API.

Owns state transitions: active, completed, completed_with_skips, ended_early.
All routes use the central session dictionary in backend.app, so audio and
camera observations refer to the same session and scenario IDs.
"""
from datetime import datetime, timezone
from importlib import import_module
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from backend.schemas import ScenarioEvent, SessionEnd, ScenarioRecovery

router = APIRouter(tags=["Sessions / Scenarios"])

def _backend():
    """Resolve central session state only when a request runs."""
    return import_module("backend.app")

def record_scenario_issue(session, scenario_id, reason):
    """Record an STT/MLLM failure on the active scenario, without adding a response."""

    ctx = _backend()
    save_sessions = ctx.save_sessions
    """Log a recoverable pipeline issue without treating it as an answer."""
    state = session.get("scenario_progress", {}).get(str(scenario_id))
    if state is not None and state.get("status") == "in_progress":
        state.setdefault("issues", []).append({
            "reason": reason,
            "recorded_at": datetime.now(timezone.utc).isoformat()
        })
        save_sessions()


@router.post("/api/session/start")
def start_session():
    """Open a new session and persist its unique ID and initial state."""

    ctx = _backend()
    sessions = ctx.sessions
    scenarios_db = ctx.scenarios_db
    save_sessions = ctx.save_sessions
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


@router.post("/api/session/end")
def end_session(data: SessionEnd):
    """Close a session; preserve the original end time on repeated calls."""

    ctx = _backend()
    sessions = ctx.sessions
    scenarios_db = ctx.scenarios_db
    save_sessions = ctx.save_sessions
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

    # A session may end early, finish normally, or finish after skipped items.
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


@router.get("/api/scenario/next")
def get_next_scenario(index: int = 0):
    """Return the scenario at a zero-based index or indicate there are no more."""

    ctx = _backend()
    scenarios_db = ctx.scenarios_db
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




@router.post("/api/scenario/start")
def start_scenario(data: ScenarioEvent):
    """Activate a scenario once; prevent overlapping or duplicate attempts."""

    ctx = _backend()
    sessions = ctx.sessions
    scenarios_db = ctx.scenarios_db
    save_sessions = ctx.save_sessions
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


@router.post("/api/scenario/complete")
def complete_scenario(data: ScenarioEvent):
    """Complete the active scenario only after its verbal answer was saved."""

    ctx = _backend()
    sessions = ctx.sessions
    scenarios_db = ctx.scenarios_db
    save_sessions = ctx.save_sessions
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


@router.post("/api/scenario/recovery")
def recover_scenario(data: ScenarioRecovery):
    """Record a retry or skip after an unsuccessful capture/processing step."""

    ctx = _backend()
    sessions = ctx.sessions
    scenarios_db = ctx.scenarios_db
    save_sessions = ctx.save_sessions
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

    # Retry keeps the scenario active; skip closes only this scenario.
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

@router.get("/api/session/{session_id}")
def get_session_results(session_id: str):
    """Return persisted session progress, captured frames and accuracy counts."""

    ctx = _backend()
    sessions = ctx.sessions
    scenarios_db = ctx.scenarios_db

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
