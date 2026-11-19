
"""Manage NAO sessions, scenarios, recovery, and verbal progress."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

import backend
from backend.schemas import ScenarioEvent, ScenarioRecovery, SessionEnd

router = APIRouter(tags=["Sessions / Scenarios"])


# -------------------- Shared Helpers --------------------

def _backend():
    """Access shared backend state and preserve test monkeypatching."""
    return backend.app


def _now():
    return datetime.now(timezone.utc).isoformat()


def _get_session(ctx, session_id, require_active=False):
    """Retrieve a session and optionally require active status."""
    session = ctx.sessions.get(session_id)

    if session is None:
        raise HTTPException(404, "Session not found.")

    if require_active and session.get("status") != "active":
        raise HTTPException(409, "Session is not active.")

    return session


def _validate_scenario(ctx, scenario_id):
    """Ensure the scenario exists in the configured database."""
    if not any(
        item["scenario_id"] == scenario_id
        for item in ctx.scenarios_db
    ):
        raise HTTPException(404, "Scenario not found.")


def _has_response(session, scenario_id):
    """Check whether a verbal answer was already saved."""
    return any(
        result["scenario_id"] == scenario_id
        for result in session["results"]
    )


def _get_active_scenario(session, scenario_id):
    """Require the requested scenario to be in progress."""
    state = session.get("scenario_progress", {}).get(str(scenario_id))

    if (
        state is None
        or state.get("status") != "in_progress"
        or session.get("active_scenario_id") != scenario_id
    ):
        raise HTTPException(
            409, "This scenario is not currently in progress."
        )

    return state


def _count_status(progress, status):
    return sum(
        state.get("status") == status
        for state in progress.values()
    )


# -------------------- Issue Logging --------------------

def record_scenario_issue(session, scenario_id, reason):
    """Log a recoverable failure without creating a verbal answer."""
    state = session.get("scenario_progress", {}).get(str(scenario_id))

    if state is not None and state.get("status") == "in_progress":
        state.setdefault("issues", []).append({
            "reason": reason,
            "recorded_at": _now()
        })
        _backend().save_sessions()


# -------------------- Session Management --------------------

@router.post("/api/session/start")
def start_session():
    """Create and persist a new session."""
    ctx = _backend()
    session_id = str(uuid4())

    ctx.sessions[session_id] = {
        "session_id": session_id,
        "status": "active",
        "started_at": _now(),
        "active_scenario_id": None,
        "scenario_progress": {},
        "results": []
    }

    ctx.save_sessions()

    return {
        "status": "success",
        "session_id": session_id,
        "total_scenarios": len(ctx.scenarios_db)
    }


@router.post("/api/session/end")
def end_session(data: SessionEnd):
    """End a session without modifying an already ended session."""
    ctx = _backend()
    session = _get_session(ctx, data.session_id)
    progress = session.get("scenario_progress", {})

    # Repeated requests preserve the original end time.
    already_ended = session.get("status") != "active"

    if not already_ended:
        if session.get("active_scenario_id") is not None:
            raise HTTPException(
                409, "Complete the active scenario before ending the session."
            )

        completed = sum(
            progress.get(str(s["scenario_id"]), {}).get("status")
            == "completed"
            for s in ctx.scenarios_db
        )
        skipped = sum(
            progress.get(str(s["scenario_id"]), {}).get("status")
            == "skipped"
            for s in ctx.scenarios_db
        )

        if completed + skipped != len(ctx.scenarios_db):
            session["status"] = "ended_early"
        elif skipped:
            session["status"] = "completed_with_skips"
        else:
            session["status"] = "completed"

        session["ended_at"] = _now()
        ctx.save_sessions()
    else:
        completed = _count_status(progress, "completed")
        skipped = _count_status(progress, "skipped")

    return {
        "status": "success",
        "session_id": data.session_id,
        "session_status": session["status"],
        "ended_at": session.get("ended_at"),
        "completed_scenarios": completed,
        "skipped_scenarios": skipped,
        "total_scenarios": len(ctx.scenarios_db),
        "already_ended": already_ended
    }


# -------------------- Scenario Management --------------------

@router.get("/api/scenario/next")
def get_next_scenario(index: int = 0):
    """Get a scenario by its zero-based index."""
    scenarios = _backend().scenarios_db

    if index < 0:
        raise HTTPException(
            400, "Scenario index cannot be negative."
        )

    if index < len(scenarios):
        return {
            "status": "success",
            "has_more": True,
            "scenario": scenarios[index]
        }

    return {
        "status": "success",
        "has_more": False,
        "message": "All scenarios completed."
    }


@router.post("/api/scenario/start")
def start_scenario(data: ScenarioEvent):
    """Activate a scenario without overlapping previous work."""
    ctx = _backend()
    session = _get_session(ctx, data.session_id, require_active=True)
    _validate_scenario(ctx, data.scenario_id)

    active_id = session.get("active_scenario_id")

    if active_id is not None:
        raise HTTPException(
            409, f"Scenario {active_id} is already in progress."
        )

    progress = session.setdefault("scenario_progress", {})
    key = str(data.scenario_id)

    if key in progress or _has_response(session, data.scenario_id):
        raise HTTPException(
            409, "This scenario was already started or evaluated."
        )

    started_at = _now()
    progress[key] = {
        "status": "in_progress",
        "started_at": started_at,
        "completed_at": None
    }

    session["active_scenario_id"] = data.scenario_id
    ctx.save_sessions()

    return {
        "status": "success",
        "session_id": data.session_id,
        "scenario_id": data.scenario_id,
        "scenario_status": "in_progress",
        "started_at": started_at
    }


@router.post("/api/scenario/complete")
def complete_scenario(data: ScenarioEvent):
    """Complete an active scenario after its verbal response is saved."""
    ctx = _backend()
    session = _get_session(ctx, data.session_id)
    if session.get("status") != "active":
        raise HTTPException(409, "Session is not active.")

    _validate_scenario(ctx, data.scenario_id)
    state = _get_active_scenario(session, data.scenario_id)

    if not _has_response(session, data.scenario_id):
        raise HTTPException(
            409, "Cannot complete a scenario without a saved verbal response."
        )

    completed_at = _now()
    state["status"] = "completed"
    state["completed_at"] = completed_at

    session["active_scenario_id"] = None
    ctx.save_sessions()

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
    """Retry or skip an active scenario after a processing failure."""
    ctx = _backend()
    session = _get_session(ctx, data.session_id, require_active=True)
    state = _get_active_scenario(session, data.scenario_id)

    if _has_response(session, data.scenario_id):
        raise HTTPException(
            409, "The scenario already has a saved verbal response."
        )

    event = {
        "action": data.action,
        "reason": data.reason,
        "recorded_at": _now()
    }

    state.setdefault("recovery_events", []).append(event)

    if data.action == "skip":
        state["status"] = "skipped"
        state["skip_reason"] = data.reason
        state["completed_at"] = event["recorded_at"]
        session["active_scenario_id"] = None

    # Retry leaves the scenario active.
    ctx.save_sessions()

    return {
        "status": "success",
        "session_id": data.session_id,
        "scenario_id": data.scenario_id,
        "scenario_status": state["status"],
        "action": data.action,
        "reason": data.reason
    }


# -------------------- Session Results --------------------

@router.get("/api/session/{session_id}")
def get_session_results(session_id: str):
    """Return session progress and verbal evaluation statistics."""
    ctx = _backend()
    session = _get_session(ctx, session_id)

    results = session["results"]
    progress = session.get("scenario_progress", {})

    summary = {
        label.lower(): sum(
            result["evaluation"] == label
            for result in results
        )
        for label in ("Correct", "Incorrect", "Unclear")
    }

    return {
        "status": "success",
        "session_id": session_id,
        "total_scenarios": len(ctx.scenarios_db),
        "total_responses": len(results),
        "session_status": session.get("status", "active"),
        "session_started_at": session.get("started_at"),
        "session_ended_at": session.get("ended_at"),
        "active_scenario_id": session.get("active_scenario_id"),
        "scenario_progress": progress,
        "skipped_scenarios": _count_status(progress, "skipped"),
        "captured_frames": session.get("captured_frames", {}),
        "results": results,
        "summary": summary
    }
